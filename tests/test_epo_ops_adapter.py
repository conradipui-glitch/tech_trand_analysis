import json
import unittest
from pathlib import Path

import httpx
from jsonschema import Draft202012Validator, FormatChecker

from tech_trend_analysis.sources.epo_ops import (
    EPOOPSAdapter, EPOOPSCredentialsMissing, EPOOPSProtocolError, EPOOPSQuery,
)

ROOT = Path(__file__).resolve().parents[1]

PATENT_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org" xmlns:ex="http://www.epo.org/exchange">
 <ops:biblio-search total-result-count="1"><ops:search-result>
  <ex:exchange-documents><ex:exchange-document family-id="6789">
   <ex:bibliographic-data>
    <ex:publication-reference><ex:document-id document-id-type="docdb">
     <ex:country>EP</ex:country><ex:doc-number>1234567</ex:doc-number>
     <ex:kind>A1</ex:kind><ex:date>20250917</ex:date>
    </ex:document-id></ex:publication-reference>
    <ex:priority-claims><ex:priority-claim><ex:document-id><ex:date>20210101</ex:date></ex:document-id></ex:priority-claim></ex:priority-claims>
    <ex:invention-title lang="de">Feststoffbatterie</ex:invention-title>
    <ex:invention-title lang="en">Solid-state battery assembly</ex:invention-title>
    <ex:applicants><ex:applicant><ex:applicant-name><ex:name>Example Energy GmbH</ex:name></ex:applicant-name>
     <ex:addressbook><ex:address><ex:country>DE</ex:country></ex:address></ex:addressbook>
    </ex:applicant></ex:applicants>
    <ex:classifications-ipcr><ex:classification-ipcr><ex:text>H01M 10/0562</ex:text></ex:classification-ipcr></ex:classifications-ipcr>
   </ex:bibliographic-data>
   <ex:abstract lang="en"><ex:p>A ceramic electrolyte architecture.</ex:p></ex:abstract>
  </ex:exchange-document></ex:exchange-documents>
 </ops:search-result></ops:biblio-search>
</ops:world-patent-data>'''


class EPOOPSAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.query = EPOOPSQuery(
            technology_direction="solid-state batteries",
            source_profile="materials_energy",
            cql='ti="solid state battery"',
        )

    def test_fail_closed_without_credentials(self):
        with self.assertRaises(EPOOPSCredentialsMissing):
            EPOOPSAdapter()

    def test_bounded_query_and_stable_id(self):
        self.assertEqual(self.query.effective_query_id, self.query.effective_query_id)
        for kwargs in ({"per_page": 26}, {"max_pages": 21}, {"cql": "x\ny"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                EPOOPSQuery("battery", "materials_energy", **({"cql": "ti=battery"} | kwargs))

    async def test_oauth_xml_mapping_and_no_backdating_from_priority(self):
        calls = []

        def mock(request):
            calls.append(request)
            if request.url.path.endswith("/auth/accesstoken"):
                self.assertTrue(request.headers["authorization"].startswith("Basic "))
                self.assertIn("grant_type=client_credentials", request.content.decode())
                return httpx.Response(200, json={"access_token": "SECRET_TEST_TOKEN", "expires_in": "1199"})
            self.assertEqual("Bearer SECRET_TEST_TOKEN", request.headers["authorization"])
            self.assertEqual("1-25", request.headers["x-ops-range"])
            self.assertEqual(self.query.cql, request.url.params["q"])
            return httpx.Response(200, content=PATENT_XML.encode())

        async with httpx.AsyncClient(transport=httpx.MockTransport(mock), base_url="https://ops.epo.org/3.2/") as client:
            adapter = EPOOPSAdapter(consumer_key="KEY", consumer_secret="SECRET", client=client)
            page = await adapter.fetch_page(self.query, state={"start": 1})
            await adapter.fetch_page(self.query, state={"start": 1})

        self.assertEqual(3, len(calls))  # one OAuth request, two authenticated searches
        self.assertIsNone(page.next_state)
        self.assertEqual(1, len(page.observations))
        obs = page.observations[0]
        self.assertEqual("epo_ops:EP1234567A1", obs["observation_id"])
        self.assertEqual("2025-09-17", obs["published_at"])
        self.assertNotEqual("2021-01-01", obs["published_at"])
        self.assertEqual("patent", obs["evidence_type"])
        self.assertEqual("Solid-state battery assembly", obs["title"])
        self.assertEqual("Example Energy GmbH", obs["actors"][0]["name"])
        self.assertEqual("DE", obs["actors"][0]["country"])
        self.assertEqual("H01M 10/0562", obs["classifications"][0]["value"])
        self.assertEqual("epo_ops:family:6789", obs["relationships"][0]["target_id"])
        self.assertEqual([], obs["collection_context"]["matched_terms"])
        self.assertIsNone(obs["analysis"]["relevance"])
        self.assertNotIn("SECRET_TEST_TOKEN", json.dumps(obs))
        schema = json.loads((ROOT / "schemas/observation.schema.json").read_text(encoding="utf-8"))
        errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(obs))
        self.assertEqual([], [x.message for x in errors])

    async def test_missing_publication_date_is_not_priority_date(self):
        xml = PATENT_XML.replace("<ex:date>20250917</ex:date>", "")

        def mock(request):
            if request.url.path.endswith("accesstoken"):
                return httpx.Response(200, json={"access_token": "T", "expires_in": 1000})
            return httpx.Response(200, content=xml)

        async with httpx.AsyncClient(transport=httpx.MockTransport(mock), base_url="https://ops.epo.org/3.2/") as client:
            adapter = EPOOPSAdapter(consumer_key="k", consumer_secret="s", client=client)
            obs = (await adapter.fetch_page(self.query, state={"start": 1})).observations[0]
        self.assertIsNone(obs["published_at"])
        self.assertTrue(obs["quality_flags"]["publication_date_missing"])

    async def test_auth_error_or_unsafe_xml_fails_closed(self):
        for status, xml in ((401, b"no"), (200, b"<!DOCTYPE foo><foo />"), (200, b"<bad")):
            with self.subTest(status=status, xml=xml):
                def mock(request):
                    if request.url.path.endswith("accesstoken"):
                        return httpx.Response(200, json={"access_token": "T", "expires_in": 1000})
                    return httpx.Response(status, content=xml)

                async with httpx.AsyncClient(transport=httpx.MockTransport(mock), base_url="https://ops.epo.org/3.2/") as client:
                    adapter = EPOOPSAdapter(consumer_key="k", consumer_secret="s", client=client)
                    with self.assertRaises(EPOOPSProtocolError):
                        await adapter.fetch_page(self.query, state={"start": 1})

    async def test_full_page_yields_bounded_continuation(self):
        query = EPOOPSQuery("battery", "materials_energy", "ti=battery", per_page=1)

        def mock(request):
            if request.url.path.endswith("accesstoken"):
                return httpx.Response(200, json={"access_token": "T", "expires_in": 1000})
            return httpx.Response(200, content=PATENT_XML)

        async with httpx.AsyncClient(transport=httpx.MockTransport(mock), base_url="https://ops.epo.org/3.2/") as client:
            adapter = EPOOPSAdapter(consumer_key="k", consumer_secret="s", client=client)
            page = await adapter.fetch_page(query, state={"start": 1})
        self.assertEqual({"start": 2}, page.next_state)


if __name__ == "__main__":
    unittest.main()
