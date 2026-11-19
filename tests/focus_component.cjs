const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const logic=require('../components/focus_challenge/logic.js');
const {execFileSync}=require('node:child_process');
const cfg=JSON.parse(execFileSync(process.env.SCORING_PYTHON||'.venv/Scripts/python.exe',['-c','import json;from core.focus_challenge import new_focus_rules;print(json.dumps(new_focus_rules()))'],{encoding:'utf8'}));
const html=fs.readFileSync('components/focus_challenge/index.html','utf8');
const code=html.match(/<script>([\s\S]*?)<\/script>/)[1];
for(const [,id] of code.matchAll(/\$\('([^']+)'\)/g)){
 assert(html.includes('id="'+id+'"'),'The restored board must contain its referenced DOM node: '+id);
}
const epoch=Date.parse('2026-11-19T20:00:00Z'),iso=ms=>new Date(epoch+ms).toISOString();
function setup(cache=new Map()){
 const elements={},messages=[],listeners={},bars=Array.from({length:3},()=>({classList:{toggle(){}}}));
 let ms=0,tick;
 function el(){return {hidden:false,disabled:false,textContent:'',style:{},children:[],handlers:{},
  classList:{flash:false,toggle(name,value){this[name]=value;}},setAttribute(){},
  appendChild(child){this.children.push(child);},addEventListener(name,handler){this.handlers[name]=handler;}};}
 const document={getElementById:id=>elements[id]??(elements[id]=el()),querySelectorAll:()=>bars,createElement:el};
 const parent={postMessage:m=>messages.push(m)};
 const window={parent,innerHeight:844,addEventListener:(name,fn)=>listeners[name]=fn};
 vm.runInNewContext(code,{document,window,FocusLogic:logic,Date,performance:{now:()=>ms},
  localStorage:{getItem:k=>cache.get(k)??null,setItem:(k,v)=>cache.set(k,v)},setInterval:fn=>{tick=fn;}});
 return {elements,messages,cache,
  render:a=>listeners.message({source:parent,data:{type:'streamlit:render',args:{attempt:a,tokens:''}}}),
  advance:n=>{ms+=n;tick();},last:()=>messages.filter(m=>m.type==='streamlit:setComponentValue').at(-1)?.value,
  pressReaction:()=>elements.react.handlers.pointerdown({preventDefault(){}})};
}
const attempt=(phase,extra={})=>({id:'attempt',revision:1,status:'running',phase,step:0,config:cfg,
 server_now:iso(0),signal_at:iso(1500),deadline:iso(3500),expires_at:iso(180000),reaction_ms:[],precision_taps:[],...extra});
const early=setup();early.render(attempt('reaction'));early.pressReaction();assert.equal(early.last().action,'fail');
const legacyEarly=setup();legacyEarly.render(attempt('reaction',{config:{...cfg,reaction_only:true,reaction_trials:3}}));
legacyEarly.pressReaction();assert.equal(legacyEarly.last().action,'false_start');
assert.equal(legacyEarly.elements.falsestart.hidden,false);
legacyEarly.elements.falsestart.handlers.pointerdown({preventDefault(){}});
assert.equal(legacyEarly.elements.falsestart.hidden,true);
const reaction=setup();reaction.render(attempt('reaction'));reaction.advance(1500);
assert.equal(reaction.elements.react.textContent,'TAP NOW');reaction.advance(250);reaction.pressReaction();
assert.equal(reaction.last().payload.elapsed_ms,250);
const handoff=setup();handoff.render(attempt('reaction'));handoff.advance(1700);handoff.pressReaction();
handoff.render(attempt('memory_ready',{revision:2,signal_at:null,deadline:iso(31700),server_now:iso(1700)}));
assert.equal(handoff.elements.ready.hidden,false);
assert.equal(handoff.elements.start.textContent,'Start memory');
assert.equal(handoff.elements.saving.textContent,'','Reaction event acknowledged by next phase');
handoff.elements.start.onclick();assert.equal(handoff.last().action,'ready');
handoff.render(attempt('memory',{revision:3,memory:[0,2,4,6,8,1,3],signal_at:iso(9000),deadline:iso(24000),server_now:iso(3050)}));
assert.equal(handoff.elements.memory.hidden,false);
const before=JSON.stringify(reaction.last());reaction.render(attempt('reaction',{server_now:iso(1750)}));
assert.equal(JSON.stringify(reaction.last()),before,'Rerenders retain pending evidence');
const resumed=setup(reaction.cache);resumed.render(attempt('reaction',{server_now:iso(1900)}));
assert.equal(resumed.last().payload.elapsed_ms,250,'Reload retries the same saved event, not a new trial');
const waiting=setup();waiting.render(attempt('reaction'));waiting.advance(1000);
waiting.render(attempt('reaction',{server_now:iso(1000)}));waiting.advance(600);
assert.equal(waiting.elements.react.textContent,'TAP NOW','Polling never resets the signal countdown');
const memory=[0,2,4,6,8,1,3],span=cfg.memory_flash_ms+cfg.memory_gap_ms;
const mem=setup();mem.render(attempt('memory',{memory,signal_at:iso(7*span),deadline:iso(7*span+15000)}));
assert.equal(mem.elements.grid.children[0].classList.flash,true);
mem.advance(span);assert.equal(mem.elements.grid.children[2].classList.flash,true);
mem.advance(6*span);assert(mem.elements.grid.children.every(b=>!b.disabled));
mem.elements.grid.children[0].onclick();assert.equal(mem.last().action,'memory');assert.equal(mem.last().payload.cell,0);
assert.equal(logic.memoryFrame(attempt('memory',{memory,signal_at:iso(7*span)}),7*span),null);
const positions=Array.from({length:12},(_,i)=>({x:120+i*60,y:880-i*60}));
const precise=setup();precise.render(attempt('precision',{positions,signal_at:iso(0),deadline:iso(12000)}));
for(let i=0;i<12;i++){precise.advance(300);precise.elements.target.onclick({stopPropagation(){}});}
assert.equal(precise.last().payload.taps.length,12);assert.equal(precise.last().payload.taps[11],3600);
assert.equal(precise.elements.target.hidden,true);
const cached=setup(precise.cache);cached.render(attempt('precision',{positions,server_now:iso(4000),signal_at:iso(0),deadline:iso(12000)}));
assert.equal(cached.last().payload.taps.length,12,'Reload recovers the final precision checkpoint');
const miss=setup();miss.render(attempt('precision',{positions,signal_at:iso(0),deadline:iso(12000)}));
miss.elements.arena.onclick({target:miss.elements.arena});assert.equal(miss.last().action,'fail');
const timeout=setup();timeout.render(attempt('precision',{positions,signal_at:iso(0),deadline:iso(12000)}));
timeout.advance(12001);assert.equal(timeout.last().action,'fail');
const saved=setup();saved.render(attempt('precision',{status:'passed',boost_ends_at:iso(3600000)}));
assert.equal(saved.elements.resultTitle.textContent,'Focus boost earned!');
assert.equal(saved.last(),undefined,'Rendering a win never requests another reward');
const qaFail=setup();qaFail.render(attempt('reaction',{status:'failed',reason:'timeout',test_mode:true}));
assert(qaFail.elements.resultText.textContent.includes('retry immediately'));
assert(!qaFail.elements.resultText.textContent.includes('two more'));
const qaWin=setup();qaWin.render(attempt('precision',{status:'passed',test_mode:true}));
assert(qaWin.elements.resultText.textContent.includes('without stacking'));
const normalFail=setup();normalFail.render(attempt('reaction',{status:'failed',reason:'timeout',test_mode:false}));
assert(normalFail.elements.resultText.textContent.includes('two more accepted check-ins'));
assert.deepEqual(logic.mergeTaps([100,200],[100,201,300],cfg),[100,200]);
console.log('Focus component checks passed: reaction timing/early tap, stable rerender/reload, memory presentation, precision prefixes/misses/timeout, and saved results.');
