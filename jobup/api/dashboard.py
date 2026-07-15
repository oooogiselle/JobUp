"""The approval dashboard (LLD §8, C12). Single-file React app served by the API
on localhost. React/Babel load from CDN (zero build step — fine for a local tool;
can graduate to a Vite build). The token is substituted into __TOKEN__ at serve
time so the same-origin page can call /api."""

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>JobUp — Approval Queue</title>
<script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
<script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
<style>
  :root { color-scheme: light dark;
    --bg:#f6f9fc; --panel:#ffffff; --panel-2:#fbfcfe; --line:#e6e9ee; --fg:#1a1f36; --muted:#697386;
    --brand:#635bff; --brand-2:#7a73ff; --brand-ink:#4b45c6; --ok:#1a9d63; --warn:#c77700; --bad:#df1b41;
    --shadow:0 1px 3px rgba(50,50,93,.09),0 1px 2px rgba(0,0,0,.06);
    --shadow-lg:0 12px 28px rgba(50,50,93,.12),0 4px 8px rgba(0,0,0,.06); --radius:12px; }
  @media (prefers-color-scheme: dark){ :root{
    --bg:#0b0f1e; --panel:#141a2c; --panel-2:#0f1526; --line:#232a40; --fg:#e7ebf3; --muted:#8b93a7;
    --brand:#8b85ff; --brand-2:#a29bff; --brand-ink:#a29bff;
    --shadow:0 1px 3px rgba(0,0,0,.4); --shadow-lg:0 14px 34px rgba(0,0,0,.55); } }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg); letter-spacing:-.006em; -webkit-font-smoothing:antialiased;
    font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif; }
  body::before{ content:""; position:fixed; inset:0 0 auto 0; height:3px; z-index:100;
    background:linear-gradient(90deg,#635bff,#8b5cf6 45%,#00d4ff); }
  header { padding:15px 24px; background:var(--panel); border-bottom:1px solid var(--line); box-shadow:var(--shadow);
    display:flex; align-items:center; gap:22px; position:relative; z-index:3; }
  header h1 { font-size:19px; margin:0; font-weight:700; letter-spacing:-.03em; display:flex; align-items:center; gap:10px; }
  header h1::before{ content:""; width:24px; height:24px; border-radius:7px;
    background:linear-gradient(135deg,#635bff,#00d4ff); box-shadow:0 2px 8px rgba(99,91,255,.4); }
  .tabs { display:flex; }
  .tab { padding:8px 2px; margin:0 12px; cursor:pointer; color:var(--muted); font-weight:600; font-size:14px;
    border-bottom:2px solid transparent; transition:.15s; }
  .tab:hover{ color:var(--fg); }
  .tab.active { color:var(--brand-ink); border-bottom-color:var(--brand); }
  .muted { color:var(--muted); font-size:13px; }
  .stats { display:flex; gap:14px; padding:18px 24px 4px; flex-wrap:wrap; }
  .stat { background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); padding:11px 18px; min-width:92px; box-shadow:var(--shadow); }
  .stat b { font-size:22px; font-weight:700; letter-spacing:-.02em; display:block; }
  .stat span { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.04em; font-weight:600; }
  .filters { display:flex; gap:10px; padding:16px 24px; flex-wrap:wrap; align-items:center; }
  input:not([type=checkbox]), select, textarea { font:inherit; padding:8px 11px; border-radius:9px; border:1px solid var(--line); background:var(--panel); color:inherit; transition:.15s; }
  input:not([type=checkbox]):focus, select:focus, textarea:focus{ outline:none; border-color:var(--brand); box-shadow:0 0 0 3px color-mix(in srgb,var(--brand) 22%,transparent); }
  input[type=checkbox]{ accent-color:var(--brand); width:16px; height:16px; }
  .filters input[type=search]{ min-width:230px; }
  .wrap { display:flex; height:calc(100vh - 205px); padding:4px 24px 22px; gap:20px; }
  .list { width:44%; max-width:560px; overflow:auto; background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); box-shadow:var(--shadow); }
  .detail, .prof { flex:1; overflow:auto; padding:24px; background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); box-shadow:var(--shadow); }
  .bulk { position:sticky; top:0; background:var(--panel); border-bottom:1px solid var(--line); padding:11px 16px; display:flex; gap:10px; align-items:center; z-index:2; border-radius:var(--radius) var(--radius) 0 0; }
  .card { padding:14px 16px; border-bottom:1px solid var(--line); cursor:pointer; display:flex; gap:11px; transition:.12s; }
  .card:hover { background:color-mix(in srgb,var(--brand) 4%,transparent); }
  .card.sel { background:color-mix(in srgb,var(--brand) 8%,transparent); box-shadow:inset 3px 0 var(--brand); }
  .card .body { flex:1; min-width:0; }
  .title { font-weight:600; letter-spacing:-.01em; }
  .badge { font-size:11px; font-weight:600; padding:3px 9px; border-radius:20px; white-space:nowrap; }
  .b-ok{ background:color-mix(in srgb,var(--ok) 14%,transparent); color:var(--ok); }
  .b-fail{ background:color-mix(in srgb,var(--bad) 13%,transparent); color:var(--bad); }
  .b-heavy{ background:color-mix(in srgb,var(--warn) 15%,transparent); color:var(--warn); }
  .b-status{ background:color-mix(in srgb,var(--muted) 14%,transparent); color:var(--muted); text-transform:capitalize; }
  .b-score{ background:color-mix(in srgb,var(--brand) 14%,transparent); color:var(--brand-ink); }
  .b-hi{ background:linear-gradient(135deg,#635bff,#00d4ff); color:#fff; }
  .card.hi{ box-shadow:inset 3px 0 #00d4ff; }
  .card.hi.sel{ box-shadow:inset 3px 0 var(--brand); }
  button { font:inherit; font-weight:600; padding:8px 15px; border-radius:9px; border:1px solid var(--line); background:var(--panel); cursor:pointer; margin-right:8px; color:var(--fg); transition:.15s; }
  button:hover { border-color:var(--muted); transform:translateY(-1px); box-shadow:var(--shadow); }
  button.primary{ background:var(--brand); color:#fff; border-color:var(--brand); box-shadow:0 2px 6px rgba(99,91,255,.35); }
  button.primary:hover{ background:var(--brand-ink); box-shadow:0 5px 14px rgba(99,91,255,.45); }
  button.warn{ background:transparent; color:var(--bad); border-color:color-mix(in srgb,var(--bad) 40%,transparent); }
  button.warn:hover{ background:color-mix(in srgb,var(--bad) 10%,transparent); }
  button.sm{ font-size:12.5px; padding:5px 11px; margin:0; }
  .alert{ background:color-mix(in srgb,var(--bad) 8%,transparent); border:1px solid color-mix(in srgb,var(--bad) 35%,transparent); padding:12px 16px; border-radius:var(--radius); margin:12px 0; }
  .alert h4{ margin:0 0 6px; color:var(--bad); }
  pre{ white-space:pre-wrap; background:var(--panel-2); border:1px solid var(--line); padding:15px; border-radius:var(--radius); overflow:auto; font-size:13px; }
  details{ background:var(--panel-2); border:1px solid var(--line); border-radius:var(--radius); padding:10px 14px; margin:12px 0; }
  summary{ cursor:pointer; font-weight:600; }
  a{ color:var(--brand-ink); text-decoration:none; } a:hover{ text-decoration:underline; }
  h2,h3{ letter-spacing:-.02em; }
  .kv{ font-size:13px; color:var(--muted); margin:3px 0; }
  .empty{ padding:48px 24px; text-align:center; color:var(--muted); }
  .form-grid{ display:grid; grid-template-columns:180px 1fr; gap:9px 14px; align-items:center; margin:10px 0; }
  .form-grid label{ font-size:13px; color:var(--muted); }
  .form-grid input.missing{ border-color:var(--warn); }
  .meter{ height:8px; border-radius:6px; background:color-mix(in srgb,var(--muted) 18%,transparent); overflow:hidden; margin:8px 0; }
  .meter > div{ height:100%; border-radius:6px; background:linear-gradient(90deg,var(--bad),var(--warn),var(--ok)); }
  .chip{ display:inline-block; font-size:12px; font-weight:500; padding:3px 10px; margin:3px 3px 0 0; border-radius:20px; background:color-mix(in srgb,var(--muted) 12%,transparent); }
  .chip.miss{ background:color-mix(in srgb,var(--warn) 15%,transparent); color:var(--warn); }
  .toast{ position:fixed; bottom:22px; right:22px; background:var(--fg); color:var(--bg); box-shadow:var(--shadow-lg); padding:11px 18px; border-radius:10px; z-index:9; font-weight:600; font-size:13.5px; animation:slideup .2s ease; }
  @keyframes slideup{ from{ opacity:0; transform:translateY(8px);} to{ opacity:1; transform:none;} }
  .prof h3{ margin:20px 0 8px; } .prof .full{ width:100%; } textarea.full{ resize:vertical; }
  kbd{ background:color-mix(in srgb,var(--muted) 15%,transparent); border-radius:5px; padding:2px 7px; font-size:12px; font-weight:600; }
  /* profile page */
  .pwrap{ max-width:780px; margin:0 auto; }
  .pcard{ background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); padding:20px 22px; margin:16px 0; box-shadow:var(--shadow); }
  .pcard h3{ margin:0 0 3px; font-size:16px; } .pcard .desc{ color:var(--muted); font-size:13px; margin:0 0 14px; }
  .upzone{ border:1.5px dashed color-mix(in srgb,var(--brand) 45%,var(--line)); border-radius:var(--radius); padding:26px; text-align:center; background:color-mix(in srgb,var(--brand) 4%,transparent); cursor:pointer; transition:.15s; }
  .upzone:hover{ background:color-mix(in srgb,var(--brand) 9%,transparent); border-color:var(--brand); }
  .upzone b{ color:var(--brand-ink); }
  .field{ margin:11px 0; } .field label{ display:block; font-size:11px; font-weight:600; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; margin-bottom:5px; }
  .field input, .field textarea{ width:100%; } .field textarea{ resize:vertical; }
  .two{ display:grid; grid-template-columns:1fr 1fr; gap:14px; } .three{ display:grid; grid-template-columns:1.4fr 1.4fr 1fr; gap:14px; }
  .exp{ border:1px solid var(--line); border-radius:10px; padding:14px 16px; margin:12px 0; position:relative; background:var(--panel-2); }
  .exp .del{ position:absolute; top:12px; right:12px; }
  .savebar{ display:flex; gap:10px; align-items:center; margin-top:14px; padding-top:14px; border-top:1px solid var(--line); }
  @media (max-width:640px){ .two,.three{ grid-template-columns:1fr; } }
</style>
</head>
<body>
<div id="root"></div>
<script type="text/babel">
const TOKEN = "__TOKEN__";
const H = { "X-JobUp-Token": TOKEN };
const qs = (o)=>Object.entries(o).filter(([,v])=>v!==""&&v!=null).map(([k,v])=>k+"="+encodeURIComponent(v)).join("&");
const req = (u,o={})=>fetch(u,{cache:"no-store",...o,headers:{...H,...(o.headers||{})}});
const J = (u,o)=>req(u,o).then(r=>r.json());
const api = {
  list:(f)=>J("/api/applications"+(qs(f)?"?"+qs(f):"")),
  companies:()=>J("/api/companies"), stats:()=>J("/api/stats"),
  get:(id)=>J("/api/applications/"+id),
  act:(id,a)=>J("/api/applications/"+id+"/"+a,{method:"POST"}),
  bulk:(action,ids)=>J("/api/applications/bulk-action",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action,ids})}),
  importJobs:(file)=>{const fd=new FormData();fd.append("file",file);return req("/api/import",{method:"POST",body:fd}).then(async r=>({ok:r.ok,body:await r.json()}));},
  patch:(id,answers)=>J("/api/applications/"+id,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({answers})}),
  assistedApply:(id)=>req("/api/applications/"+id+"/assisted-apply",{method:"POST"}).then(async r=>({ok:r.ok,body:await r.json()})),
  openPdf:(id)=>req("/api/applications/"+id+"/resume.pdf").then(r=>r.blob()).then(b=>window.open(URL.createObjectURL(b),"_blank")),
  coverLetter:(id)=>req("/api/applications/"+id+"/cover-letter",{method:"POST"}).then(async r=>({ok:r.ok,body:await r.json()})),
  finalize:(id)=>req("/api/applications/"+id+"/finalize",{method:"POST"}).then(async r=>({ok:r.ok,body:await r.json()})),
  openCoverPdf:(id)=>req("/api/applications/"+id+"/cover-letter.pdf").then(r=>r.blob()).then(b=>window.open(URL.createObjectURL(b),"_blank")),
  openPackage:(id)=>req("/api/applications/"+id+"/package.zip").then(r=>r.blob()).then(b=>{const u=URL.createObjectURL(b);const a=document.createElement("a");a.href=u;a.download="jobup-package.zip";a.click();URL.revokeObjectURL(u);}),
  runStatus:()=>J("/api/run"),
  triggerRun:()=>req("/api/run",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({})}).then(async r=>({ok:r.ok,body:await r.json()})),
  profile:()=>J("/api/profile"),
  saveProfile:(p)=>J("/api/profile",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)}),
  saveAnswers:(a)=>J("/api/answers-profile",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(a)}),
  upload:(file)=>{const fd=new FormData();fd.append("file",file);return req("/api/profile/upload",{method:"POST",body:fd}).then(async r=>({ok:r.ok,body:await r.json()}));},
  resumes:()=>J("/api/resumes"),
  getResume:(id)=>J("/api/resumes/"+id),
  saveResume:(body)=>J("/api/resumes",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}),
  delResume:(id)=>J("/api/resumes/"+id,{method:"DELETE"}),
  setDefaultResume:(id)=>J("/api/resumes/"+id+"/default",{method:"POST"}),
  openResumePdf:(id)=>req("/api/resumes/"+id+"/pdf").then(r=>r.blob()).then(b=>window.open(URL.createObjectURL(b),"_blank")),
};
const fmtDate=(s)=>s?new Date(s).toLocaleDateString(undefined,{year:"numeric",month:"short",day:"numeric"}):"—";
const LABELS={work_authorization:"Work authorization",needs_sponsorship:"Needs visa sponsorship",willing_to_relocate:"Willing to relocate",onsite_ok:"Open to onsite / hybrid",earliest_start_date:"Earliest start date",degree:"Degree",graduation_date:"Graduation date",salary_expectation:"Salary expectation",why_this_company:"Why this company"};
const labelFor=(k)=>LABELS[k]||k;
const ToastCtx = React.createContext(()=>{});

function Badges({a}){return(<>
  {a.score!=null&&a.score>=0.8&&<span className="badge b-hi">★ high fit</span>}{" "}
  {a.score!=null&&<span className="badge b-score">match {(a.score*100).toFixed(0)}%</span>}{" "}
  {a.factual_check_passed?<span className="badge b-ok">✓ verified</span>:<span className="badge b-fail">⚠ factual</span>}{" "}
  {a.needs_heavy_rewrite&&<span className="badge b-heavy">heavy rewrite?</span>}{" "}
  <span className="badge b-status">{a.status}</span>
</>);}

function Ats({ats}){
  if(!ats||ats.jd_total===0) return null;
  return(<details open>
    <summary>ATS keyword match — {(ats.score*100).toFixed(0)}% ({ats.present.length}/{ats.jd_total})</summary>
    <div className="meter"><div style={{width:(ats.score*100)+"%"}}/></div>
    <div className="kv">In your resume:</div>
    <div>{ats.present.map(k=><span key={k} className="chip">{k}</span>)}{ats.present.length===0&&<span className="muted">none</span>}</div>
    {ats.missing.length>0&&<><div className="kv" style={{marginTop:6}}>Missing (add if you genuinely have it):</div>
      <div>{ats.missing.map(k=><span key={k} className="chip miss">{k}</span>)}</div></>}
  </details>);
}

function JD({sections}){
  if(!sections||sections.length===0) return <pre>(no description stored)</pre>;
  return <div>{sections.map((s,i)=>(<div key={i} style={{marginBottom:10}}>
    <div style={{fontWeight:600,marginBottom:2}}>{s.heading}</div>
    <ul style={{margin:"4px 0"}}>{s.items.filter(it=>it.type==="bullet").map((it,j)=><li key={j}>{it.text}</li>)}</ul>
    {s.items.filter(it=>it.type==="text").map((it,j)=><p key={j} style={{margin:"4px 0"}}>{it.text}</p>)}
  </div>))}</div>;
}

function AnswerForm({d,onSaved}){
  const toast=React.useContext(ToastCtx);
  const init={...(d.answers||{})}; (d.unanswered||[]).forEach(k=>{if(!(k in init))init[k]="";});
  const [vals,setVals]=React.useState(init); const keys=Object.keys(init);
  React.useEffect(()=>{const i={...(d.answers||{})};(d.unanswered||[]).forEach(k=>{if(!(k in i))i[k]="";});setVals(i);},[d.id]);
  if(keys.length===0) return null;
  const save=()=>api.patch(d.id,vals).then(()=>{toast("Answers saved");onSaved&&onSaved();});
  return(<details open>
    <summary>Application answers (autofilled — review &amp; edit)</summary>
    <div className="form-grid">{keys.map(k=>(<React.Fragment key={k}>
      <label>{labelFor(k)}</label>
      <input value={vals[k]??""} className={(vals[k]??"")===""?"missing":""} onChange={e=>setVals({...vals,[k]:e.target.value})}/>
    </React.Fragment>))}</div>
    <button className="primary sm" onClick={save}>Save answers</button>
  </details>);
}

function Detail({id,onChanged}){
  const toast=React.useContext(ToastCtx);
  const [d,setD]=React.useState(null); const [msg,setMsg]=React.useState(""); const [clMsg,setClMsg]=React.useState("");
  const reload=()=>api.get(id).then(setD);
  React.useEffect(()=>{if(id){setMsg("");setClMsg("");api.get(id).then(setD);}},[id]);
  const genCover=()=>{setClMsg("Generating (grounded + verified)…");api.coverLetter(id).then(res=>{setClMsg(res.ok?"":"⚠ "+(res.body.detail||"failed"));reload();toast(res.ok?"cover letter ready":"cover letter failed");});};
  // Approve = advance to 'approved' AND generate the cover letter + "why this
  // company" on the spot, then the apply package is one download away.
  const approve=()=>{setClMsg("Approving → generating cover letter + answers (grounded + verified)…");
    api.finalize(id).then(res=>{setClMsg(res.ok?"":"⚠ "+(res.body.detail||"failed"));reload();onChanged();toast(res.ok?"approved — package ready":"approve failed");});};
  if(!id) return <div className="empty">Select an application. Shortcuts: <kbd>j</kbd>/<kbd>k</kbd> move · <kbd>a</kbd> approve · <kbd>s</kbd> skip · <kbd>o</kbd> open job</div>;
  if(!d) return <div className="empty">Loading…</div>;
  const r=d.tailored_resume||{};
  const act=(a)=>api.act(id,a).then(()=>{reload();onChanged();toast(a.replace("-"," "));});
  const apply=()=>{setMsg("Launching browser…");api.assistedApply(id).then(res=>setMsg(res.ok?"Browser opening — fields autofilling + resume attached. Review & submit yourself.":"⚠ "+(res.body.detail||"could not launch")));};
  return(<div>
    <h2 style={{margin:"0 0 4px"}}>{d.title}</h2>
    <div className="kv">{d.company} · {d.location||"—"} · team: {d.enrichment?.team||"unknown"} · posted {fmtDate(d.posted_at)}</div>
    <div style={{margin:"10px 0"}}><Badges a={{...d,...r}}/></div>
    {!r.factual_check_passed&&(<div className="alert"><h4>Factual check failed — do not send as-is</h4>
      <div>Claims not supported by your experience library{r.revisions?` (auto-revised ${r.revisions}× and still unsupported)`:""}:</div>
      <ul>{(r.unsupported_claims||[]).map((c,i)=><li key={i}>{c}</li>)}</ul></div>)}
    <div style={{margin:"14px 0"}}>
      {d.status==="prepared"&&<button className="primary" onClick={approve}>Approve &amp; generate package</button>}
      {d.status==="approved"&&<button className="primary" onClick={()=>api.openPackage(id)}>Download apply package ↓</button>}
      {d.status==="approved"&&<button className="primary" onClick={()=>act("mark-applied")}>I applied ✔</button>}
      {["prepared","approved"].includes(d.status)&&<button className="warn" onClick={()=>act("skip")}>Skip</button>}
      <button onClick={apply}>Assisted apply — open, autofill &amp; attach PDF ↗</button>
      {d.apply_url&&<a href={d.apply_url} target="_blank" rel="noreferrer"><button>Open job ↗</button></a>}
    </div>
    {msg&&<div className="kv" style={{marginTop:-6}}>{msg}</div>}
    <div className="kv">The agent never submits — you download the package, apply yourself, then mark it applied.</div>
    <Ats ats={d.ats}/>
    <AnswerForm d={d} onSaved={onChanged}/>
    <details><summary>Job description</summary><JD sections={d.description_sections}/></details>
    <h3>Tailored resume {r.mode?"("+r.mode+")":""} <button className="sm" onClick={()=>api.openPdf(id)}>Resume PDF ↧</button></h3>
    <pre>{r.resume_markdown||"(none)"}</pre>
    <h3>Cover letter
      {" "}<button className="sm" onClick={genCover}>{d.cover_letter?"Regenerate":"Generate"}</button>
      {d.cover_letter&&<button className="sm" onClick={()=>api.openCoverPdf(id)}>PDF ↧</button>}
    </h3>
    {clMsg&&<div className="kv">{clMsg}</div>}
    {d.cover_letter&&!d.cover_letter_ok&&<div className="alert"><h4>Cover letter failed factual check</h4><div>May contain claims not in your experience library — review before sending.</div></div>}
    {d.cover_letter&&<pre>{d.cover_letter}</pre>}
    {!d.cover_letter&&!clMsg&&<div className="kv">Approve (or click Generate) for a grounded, fact-checked cover letter + "why this company".</div>}
    {d.why_this_company&&<><h3>Why this company{d.why_this_company_ok?"":" ⚠"}</h3><pre>{d.why_this_company}</pre></>}
  </div>);
}

function Queue({toast}){
  const [apps,setApps]=React.useState([]); const [companies,setCompanies]=React.useState([]);
  const [stats,setStats]=React.useState(null); const [sel,setSel]=React.useState(null);
  const [checked,setChecked]=React.useState(new Set());
  const [needsAttn,setNeedsAttn]=React.useState(false);
  const [run,setRun]=React.useState(null);
  const [f,setF]=React.useState({q:"",company:"",min_score:"",status:"",posted_since:"",order:"fit"});
  const importRef=React.useRef();
  const query=React.useMemo(()=>({...f,...(needsAttn?{needs_attention:true}:{})}),[f,needsAttn]);
  const refresh=React.useCallback(()=>{api.list(query).then(setApps);api.stats().then(setStats);},[query]);
  const doImport=(e)=>{const file=e.target.files[0]; if(!file)return; toast("Importing + tailoring…");
    api.importJobs(file).then(res=>{ if(res.ok){toast(`Imported ${res.body.imported} of ${res.body.parsed}`);refresh();} else toast("⚠ "+(res.body.detail||"import failed")); });};
  const doRun=()=>{api.triggerRun().then(res=>{ if(res.ok){toast("Run started — discovering + tailoring…");setRun({running:true,phase:"discovering"});}else toast("⚠ "+(res.body.detail||"could not start run")); });};
  React.useEffect(()=>{refresh();},[refresh]);
  React.useEffect(()=>{const t=setInterval(refresh,15000);return ()=>clearInterval(t);},[refresh]);  // auto-refresh
  React.useEffect(()=>{  // poll run status while a run is active
    const t=setInterval(()=>api.runStatus().then(s=>{setRun(s); if(s&&!s.running&&s.phase!=="idle"){clearInterval(t);refresh();
      if(s.phase==="done")toast(`Run done — ${s.summary?.prepared??0} prepared`); if(s.phase==="error")toast("⚠ run error: "+(s.error||""));}}),3000);
    return ()=>clearInterval(t);},[run&&run.running]);
  React.useEffect(()=>{api.runStatus().then(setRun);},[]);
  React.useEffect(()=>{api.companies().then(setCompanies);},[apps.length]);
  const upd=(k)=>(e)=>setF({...f,[k]:e.target.value});
  const idx=apps.findIndex(a=>a.id===sel);
  const bulk=(action)=>{const ids=[...checked];api.bulk(action,ids).then(()=>{setChecked(new Set());refresh();toast(action+" "+ids.length);});};
  const toggle=(id)=>{const s=new Set(checked);s.has(id)?s.delete(id):s.add(id);setChecked(s);};
  React.useEffect(()=>{
    const onKey=(e)=>{
      if(["INPUT","TEXTAREA","SELECT"].includes(document.activeElement.tagName)) return;
      if(e.key==="j"&&idx<apps.length-1) setSel(apps[idx+1].id);
      else if(e.key==="k"&&idx>0) setSel(apps[idx-1].id);
      else if(e.key==="a"&&sel) api.act(sel,"approve").then(()=>{refresh();toast("approved");});
      else if(e.key==="s"&&sel) api.act(sel,"skip").then(()=>{refresh();toast("skipped");});
      else if(e.key==="o"&&sel){const a=apps[idx]; if(a) api.get(sel).then(d=>d.apply_url&&window.open(d.apply_url,"_blank"));}
      else if(e.key==="x"&&sel) toggle(sel);
    };
    window.addEventListener("keydown",onKey); return ()=>window.removeEventListener("keydown",onKey);
  },[apps,idx,sel,checked]);
  return(<>
    {stats&&<div className="stats">
      <div className="stat"><b>{stats.total}</b><span>total</span></div>
      {["prepared","approved","applied","skipped"].map(s=><div key={s} className="stat"><b>{stats.by_status[s]||0}</b><span>{s}</span></div>)}
      <div className="stat"><b>{stats.avg_score!=null?(stats.avg_score*100).toFixed(0)+"%":"—"}</b><span>avg fit</span></div>
      <div className="stat"><b>{stats.new_today}</b><span>new today</span></div>
    </div>}
    <div className="filters">
      <input type="search" placeholder="Search title / company / team…" value={f.q} onChange={upd("q")}/>
      <select value={f.company} onChange={upd("company")}><option value="">All companies</option>{companies.map(c=><option key={c} value={c}>{c}</option>)}</select>
      <select value={f.min_score} onChange={upd("min_score")}><option value="">Any fit</option><option value="0.6">≥60%</option><option value="0.7">≥70%</option><option value="0.8">≥80%</option></select>
      <select value={f.status} onChange={upd("status")}><option value="">Any status</option>{["prepared","approved","applied","skipped"].map(s=><option key={s} value={s}>{s}</option>)}</select>
      <select value={f.order} onChange={upd("order")}><option value="fit">Sort: best fit</option><option value="recent">Sort: newest</option></select>
      <label className="muted">since <input type="date" value={f.posted_since} onChange={upd("posted_since")}/></label>
      <button className={"sm"+(needsAttn?" warn":"")} onClick={()=>setNeedsAttn(v=>!v)} title="Resumes that failed the factual check">{needsAttn?"⚠ Needs attention ✓":"⚠ Needs attention"}</button>
      <input ref={importRef} type="file" accept=".csv,.json" style={{display:"none"}} onChange={doImport}/>
      <button className="primary sm" style={{marginLeft:"auto"}} onClick={doRun} disabled={run&&run.running} title="Discover fresh postings and tailor them">{run&&run.running?("Running: "+(run.phase||"…")):"Run pipeline ▶"}</button>
      <button className="sm" onClick={()=>importRef.current.click()} title="Import jobs from a CSV/JSON (N8N, LinkedIn export, spreadsheet…)">Import jobs ↥</button>
    </div>
    <div className="wrap">
      <div className="list">
        <div className="bulk">
          <input type="checkbox" checked={checked.size>0&&checked.size===apps.length} onChange={e=>setChecked(e.target.checked?new Set(apps.map(a=>a.id)):new Set())}/>
          <span className="muted">{checked.size} selected</span>
          {checked.size>0&&<><button className="primary sm" onClick={()=>bulk("approve")}>Approve</button><button className="warn sm" onClick={()=>bulk("skip")}>Skip</button></>}
        </div>
        {apps.length===0&&<div className="empty">{needsAttn?"Nothing needs attention — all resumes passed the factual check.":"No matching applications. Click “Run pipeline” to discover + tailor fresh postings."}</div>}
        {apps.map(a=>(<div key={a.id} className={"card"+(sel===a.id?" sel":"")+(a.score!=null&&a.score>=0.8?" hi":"")} onClick={()=>setSel(a.id)}>
          <input type="checkbox" checked={checked.has(a.id)} onClick={e=>e.stopPropagation()} onChange={()=>toggle(a.id)}/>
          <div className="body">
            <div className="title">{a.title}</div>
            <div className="kv">{a.company} · {a.location||"—"} · posted {fmtDate(a.posted_at)}</div>
            <div style={{marginTop:6}}><Badges a={a}/></div>
          </div>
        </div>))}
      </div>
      <div className="detail"><Detail id={sel} onChanged={refresh}/></div>
    </div>
  </>);
}

function Field({label,children}){return <div className="field"><label>{label}</label>{children}</div>;}

function Profile({toast}){
  const [p,setP]=React.useState(null); const [answers,setAnswers]=React.useState({});
  const [busy,setBusy]=React.useState(""); const [newKey,setNewKey]=React.useState("");
  const [resumes,setResumes]=React.useState([]); const [viewing,setViewing]=React.useState(null);
  const fileRef=React.useRef();
  React.useEffect(()=>{api.profile().then(d=>{setP(d.profile);setAnswers(d.answers||{});});api.resumes().then(setResumes);},[]);
  if(!p) return <div className="empty">Loading…</div>;
  const upload=(e)=>{const file=e.target.files[0]; if(!file)return; setBusy("Extracting your resume…");
    api.upload(file).then(res=>{setBusy(""); if(res.ok){setP(res.body.profile);setAnswers(res.body.answers||{});api.resumes().then(setResumes);toast("Resume extracted ✓");} else toast("⚠ "+(res.body.detail||"upload failed"));});};
  const saveFromProfile=()=>api.saveResume({from_profile:true}).then(r=>{setResumes(r.resumes);toast("Saved to library ✓");});
  const delRes=(id)=>api.delResume(id).then(r=>{setResumes(r.resumes);if(viewing&&viewing.id===id)setViewing(null);});
  const viewRes=(id)=>api.getResume(id).then(setViewing);
  const makeDefault=(id)=>api.setDefaultResume(id).then(r=>{setResumes(r.resumes);toast("Default resume set ✓");});
  const setField=(k,v)=>setP({...p,[k]:v});
  const setExp=(i,k,v)=>{const e=[...p.experience];e[i]={...e[i],[k]:v};setP({...p,experience:e});};
  const addExp=()=>setP({...p,experience:[...(p.experience||[]),{title:"",org:"",dates:"",bullets:[]}]});
  const delExp=(i)=>setP({...p,experience:p.experience.filter((_,j)=>j!==i)});
  const saveProfile=()=>api.saveProfile(p).then(()=>toast("Profile saved ✓"));
  const saveAns=()=>api.saveAnswers(answers).then(()=>toast("Answers saved ✓"));
  const addAns=()=>{const k=newKey.trim(); if(k&&!(k in answers)){setAnswers({...answers,[k]:""});setNewKey("");}};
  const delAns=(k)=>{const a={...answers};delete a[k];setAnswers(a);};
  const expCount=(p.experience||[]).length;
  return(<div className="pwrap">
    <h2 style={{margin:"4px 0 2px"}}>Your profile</h2>
    <p className="muted" style={{marginTop:0}}>Everything here grounds matching, tailoring & autofill. Nothing is invented from your resume — you can edit anything below.</p>

    <div className="pcard">
      <input ref={fileRef} type="file" accept=".pdf,.txt,.md" style={{display:"none"}} onChange={upload}/>
      <div className="upzone" onClick={()=>fileRef.current.click()}>
        {busy ? <span>{busy}</span>
          : <><div style={{fontSize:15}}>📄 <b>Upload your resume</b> to auto-fill this page</div>
              <div className="muted" style={{marginTop:4}}>PDF, TXT, or MD · click to choose a file</div></>}
      </div>
    </div>

    <div className="pcard">
      <h3>Resume library</h3>
      <div className="desc">Your saved resumes. Each job you prepare gets its own auto-tailored version — this is the base they're remade from.</div>
      {resumes.length===0&&<div className="muted">No resumes yet — upload one above, or save your profile as a resume.</div>}
      {resumes.map(rz=>(<div key={rz.id} className="exp" style={{display:"flex",alignItems:"center",gap:10}}>
        <div style={{flex:1}}>
          <b>{rz.name}</b> {rz.is_default&&<span className="badge b-score">★ default</span>}
          <div className="kv">{rz.source} · {fmtDate(rz.created_at)} · {rz.size} chars</div>
        </div>
        {!rz.is_default&&<button className="sm" onClick={()=>makeDefault(rz.id)}>Set default</button>}
        <button className="sm" onClick={()=>viewRes(rz.id)}>View</button>
        <button className="sm" onClick={()=>api.openResumePdf(rz.id)}>PDF ↧</button>
        <button className="warn sm" onClick={()=>delRes(rz.id)}>Delete</button>
      </div>))}
      {viewing&&<div style={{marginTop:8}}><div className="kv">{viewing.name}</div><pre>{viewing.markdown}</pre></div>}
      <div className="savebar"><button className="primary" onClick={saveFromProfile}>Save current profile as resume</button></div>
    </div>

    <div className="pcard">
      <h3>Basics</h3>
      <div className="desc">Who you are and what you're looking for.</div>
      <div className="two">
        <Field label="Name"><input value={p.name||""} onChange={e=>setField("name",e.target.value)}/></Field>
        <Field label="Work authorization"><input value={p.work_authorization||""} placeholder="e.g. US citizen" onChange={e=>setField("work_authorization",e.target.value)}/></Field>
      </div>
      <div className="two">
        <Field label="Needs visa sponsorship?">
          <select value={p.needs_sponsorship===true?"yes":p.needs_sponsorship===false?"no":""} onChange={e=>setField("needs_sponsorship",e.target.value===""?null:e.target.value==="yes")}>
            <option value="">—</option><option value="no">No</option><option value="yes">Yes</option>
          </select>
        </Field>
        <Field label="Target locations (comma-separated)"><input value={(p.locations||[]).join(", ")} onChange={e=>setField("locations",e.target.value.split(",").map(s=>s.trim()).filter(Boolean))}/></Field>
      </div>
      <Field label="Skills (comma-separated)"><input value={(p.skills||[]).join(", ")} onChange={e=>setField("skills",e.target.value.split(",").map(s=>s.trim()).filter(Boolean))}/></Field>
      <Field label="Summary"><textarea rows="2" value={p.summary||""} onChange={e=>setField("summary",e.target.value)}/></Field>
    </div>

    <div className="pcard">
      <h3>Experience <span className="muted" style={{fontWeight:400}}>· {expCount}</span></h3>
      <div className="desc">The only facts used to tailor your resume — keep bullets accurate.</div>
      {(p.experience||[]).map((ex,i)=>(<div key={i} className="exp">
        <button className="warn sm del" onClick={()=>delExp(i)}>Remove</button>
        <div className="three">
          <Field label="Title"><input value={ex.title||""} onChange={e=>setExp(i,"title",e.target.value)}/></Field>
          <Field label="Organization"><input value={ex.org||""} onChange={e=>setExp(i,"org",e.target.value)}/></Field>
          <Field label="Dates"><input value={ex.dates||""} onChange={e=>setExp(i,"dates",e.target.value)}/></Field>
        </div>
        <Field label="Bullets (one per line)"><textarea rows="3" value={(ex.bullets||[]).join("\n")} onChange={e=>setExp(i,"bullets",e.target.value.split("\n").filter(Boolean))}/></Field>
      </div>))}
      <button className="sm" onClick={addExp}>+ Add experience</button>
      <div className="savebar"><button className="primary" onClick={saveProfile}>Save profile</button></div>
    </div>

    <div className="pcard">
      <h3>Application answers</h3>
      <div className="desc">Autofilled into applications by "Assisted apply". Empty ones are flagged.</div>
      <div className="two">{Object.keys(answers).map(k=>(
        <Field key={k} label={k}>
          <div style={{display:"flex",gap:6}}>
            <input style={{flex:1}} value={answers[k]??""} onChange={e=>setAnswers({...answers,[k]:e.target.value})}/>
            <button className="sm" title="remove" onClick={()=>delAns(k)}>✕</button>
          </div>
        </Field>))}</div>
      <div className="savebar">
        <input placeholder="new field name" value={newKey} onChange={e=>setNewKey(e.target.value)} onKeyDown={e=>e.key==="Enter"&&addAns()}/>
        <button className="sm" onClick={addAns}>+ Add field</button>
        <button className="primary" style={{marginLeft:"auto"}} onClick={saveAns}>Save answers</button>
      </div>
    </div>
  </div>);
}

function App(){
  const [tab,setTab]=React.useState("queue");
  const [toast,setToast]=React.useState("");
  const show=(m)=>{setToast(m);setTimeout(()=>setToast(""),2200);};
  return(<ToastCtx.Provider value={show}>
    <header>
      <h1>JobUp</h1>
      <div className="tabs">
        <div className={"tab"+(tab==="queue"?" active":"")} onClick={()=>setTab("queue")}>Queue</div>
        <div className={"tab"+(tab==="profile"?" active":"")} onClick={()=>setTab("profile")}>Profile</div>
      </div>
      <span className="muted" style={{marginLeft:"auto"}}>you press apply — the agent never submits</span>
    </header>
    {tab==="queue"?<Queue toast={show}/>:<Profile toast={show}/>}
    {toast&&<div className="toast">{toast}</div>}
  </ToastCtx.Provider>);
}
ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
</script>
</body>
</html>
"""
