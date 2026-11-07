async page => {
  const timeout = ARGS.timeoutMs || 45000;
  const cols = ARGS.columns || ['organization_id', 'canonical_organization_id', 'provider_id'];
  const out = { ok: false, state: 'goto' };
  let captured = null;
  const onReq = r => {
    if (!captured && r.method() === 'POST' && /\/widget\/data(\?|$)/.test(r.url())) captured = { url: r.url(), headers: r.headers(), body: r.postData() };
  };
  page.on('request', onReq);
  try {
    const url = /^https?:\/\//.test(ARGS.url) ? ARGS.url : (ARGS.origin || '') + ARGS.url;
    const firstResp = page.waitForResponse(r => r.request().method() === 'POST' && /\/widget\/data(\?|$)/.test(r.url()), { timeout });
    firstResp.catch(() => {});
    const nav = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    out.status = nav ? nav.status() : null;
    out.final = await page.evaluate(() => location.pathname + location.search);
    out.state = 'wait-data';
    const r1 = await firstResp.catch(() => null);
    if (!r1) {
      await page.waitForSelector('.alert-danger', { timeout: 8000 }).catch(() => null);
      out.alertText = await page.evaluate(() => { const a = document.querySelector('.alert-danger'); return a ? a.innerText.trim().slice(0, 200) : null; });
      out.state = out.alertText ? 'denied' : 'no-data';
      return out;
    }
    out.firstStatus = r1.status();
    const b1 = await r1.json().catch(() => null);
    out.firstPageRows = b1 && b1.value && b1.value.Table ? b1.value.Table.RowCount : null;
    out.state = 'replay';
    const body = JSON.parse(captured.body);
    body.pagingPageSize = ARGS.pageSize || 5000;
    body.pagingStartIndex = 0;
    const headers = {};
    for (const k of ['authorization', 'content-type', 'accept', 'origin', 'referer']) if (captured.headers[k]) headers[k] = captured.headers[k];
    const rr = await page.request.post(captured.url, { headers, data: JSON.stringify(body), timeout });
    out.replayStatus = rr.status();
    const j = await rr.json().catch(() => null);
    const t = j && j.value && j.value.Table;
    if (!t) { out.state = 'replay-no-table'; return out; }
    out.rowCount = t.RowCount;
    out.truncated = t.Truncated;
    out.scope = {};
    for (const c of cols) {
      const dc = (t.DataColumns || []).find(d => d.Name === c);
      out.scope[c] = dc ? [...new Set((dc.Values || []).map(v => (v == null ? null : Number(v))))].sort((a, b) => a - b).slice(0, 25) : 'absent';
    }
    out.ok = out.replayStatus === 200 && typeof out.rowCount === 'number';
    out.state = 'done';
    return out;
  } catch (e) {
    return { ...out, errorClass: e.name, detail: String(e.message).split('\n')[0].slice(0, 300) };
  } finally {
    page.off('request', onReq);
  }
}
