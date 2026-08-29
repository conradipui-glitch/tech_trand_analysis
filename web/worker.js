const json = (body, init = {}) => new Response(JSON.stringify(body), {
  ...init,
  headers: { "content-type": "application/json; charset=utf-8", ...(init.headers || {}) },
});

async function currentData(env, requestUrl) {
  const url = new URL("/data/current.json", requestUrl);
  const response = await env.ASSETS.fetch(new Request(url));
  if (!response.ok) throw new Error("current snapshot unavailable");
  return response.json();
}

function matchCase(data, query) {
  const needle = String(query || "").trim().toLowerCase();
  if (!needle) return null;
  return data.cases.find((item) => {
    const haystack = [item.id, item.label, ...(item.aliases || [])].join(" ").toLowerCase();
    return haystack.includes(needle) || needle.includes(item.id.toLowerCase());
  }) || null;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/api/health") {
      return json({
        ok: true,
        service: "tech-trend-analysis",
        shell: "operator-v0",
        analyst_mode: "deepseek-ci-batch-only",
        dynamic_analysis: false,
      });
    }

    if (url.pathname === "/api/current" && request.method === "GET") {
      try {
        return json(await currentData(env, request.url));
      } catch (error) {
        return json({ ok: false, error: String(error) }, { status: 503 });
      }
    }

    if (url.pathname === "/api/analysis" && request.method === "GET") {
      try {
        const data = await currentData(env, request.url);
        const item = matchCase(data, url.searchParams.get("direction"));
        if (!item) {
          return json({
            ok: false,
            status: "not_computed",
            available: data.cases.map(({ id, label }) => ({ id, label })),
          }, { status: 404 });
        }
        return json({ ok: true, item, generated_at: data.generated_at });
      } catch (error) {
        return json({ ok: false, error: String(error) }, { status: 503 });
      }
    }

    if (url.pathname === "/api/analyze" && request.method === "POST") {
      let body = {};
      try { body = await request.json(); } catch {}
      const data = await currentData(env, request.url);
      const item = matchCase(data, body.direction);
      if (item) return json({ ok: true, status: "snapshot", item, generated_at: data.generated_at });
      return json({
        ok: false,
        status: "not_computed",
        message: "Web shell is live, but arbitrary-direction TOP-15 jobs are not wired yet. The detector core is currently being calibrated before the TOP-15 assembler is connected.",
        available: data.cases.map(({ id, label }) => ({ id, label })),
      }, { status: 409 });
    }

    return env.ASSETS.fetch(request);
  },
};
