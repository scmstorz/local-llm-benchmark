/** Isolated-resource SDK driver for the writing-workflow prototype.
 * Transport is supplied by the controller. This driver does not configure Ollama.
 * Only the seven bounded tools are enabled; no discovered prompts/skills/plugins.
 */
import { readFileSync,writeFileSync,mkdirSync } from 'node:fs';
import { resolve,dirname } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createAgentSession,createExtensionRuntime,ModelRuntime,SessionManager,SettingsManager } from '@earendil-works/pi-coding-agent';

export const TOOL_NAMES=['list_documents','read_document','search_documents','calculate','write_note','read_note','submit_article'];
const schemas={
 list_documents:{},
 read_document:{source_id:{type:'string'},offset:{type:'integer'},max_chars:{type:'integer'}},
 search_documents:{query:{type:'string'},source_id:{type:'string'},offset:{type:'integer'},max_hits:{type:'integer'}},
 calculate:{expression:{type:'string'},values:{type:'object',additionalProperties:{type:'integer'}}},
 write_note:{name:{type:'string'},text:{type:'string'}},
 read_note:{name:{type:'string'},offset:{type:'integer'},max_chars:{type:'integer'}},
 submit_article:{article:{type:'string'}},
};
const required={list_documents:[],read_document:['source_id'],search_documents:['query'],calculate:['expression'],write_note:['name','text'],read_note:['name'],submit_article:['article']};

export function loopback(value){
 const u=new URL(value);
 if(u.protocol!=='http:'||u.hostname!=='127.0.0.1'||!u.port||u.port==='11434'||u.username||u.password||u.pathname!=='/'||u.search||u.hash)throw Error('An explicit loopback controller is required');
 return u.origin;
}

export function modelLimits(policy){
 const context=policy.context_tokens,output=policy.request_output_ceiling;
 if(!Number.isSafeInteger(context)||context<2||!Number.isSafeInteger(output)||output<1||output>=context)throw Error('Explicit model/context-bound request limits are required');
 return {contextWindow:context,maxTokens:output};
}

export const DELIVERY_V2='tool_or_regular_final_v2';
export function regularFinalResponse(events){
 // Only the actual last completed agent turn. Never scan backwards for prose.
 let index=events.length-1;
 while(index>=0&&events[index].type==='agent_settled')index--;
 const end=events[index];
 if(end?.type!=='agent_end'||end.willRetry===true||!Array.isArray(end.messages))return null;
 const pending=new Set();
 for(const message of end.messages){
  if(message.role==='assistant')for(const block of message.content??[])if(block.type==='toolCall')pending.add(block.id);
  if(message.role==='toolResult')pending.delete(message.toolCallId);
 }
 const last=end.messages.at(-1);
 if(pending.size||last?.role!=='assistant'||last.stopReason!=='stop'||last.errorMessage||last.content?.some(b=>b.type==='toolCall'))return null;
 const article=(last.content??[]).filter(b=>b.type==='text').map(b=>b.text).join('');
 if(!article.trim()||!/^ollama-native-[1-9][0-9]*$/.test(last.responseId??''))return null;
 return {article,response_id:last.responseId};
}

export async function run(policy){
 const limits=modelLimits(policy);
 const gateway=loopback(policy.gateway);const runRoot=resolve(policy.run_root);const workspace=resolve(policy.workspace);
 const expectedMode={offline_replay:'synthetic_only',technical_probe:'local_native_technical',study_replay:'synthetic_only',scored_trial:'local_native_study'}[policy.mode];
 if(dirname(workspace)!==runRoot||!expectedMode)throw Error('An explicit bound controller mode is required');
 const identity=await fetch(gateway+'/offline-identity',{redirect:'error'});
 if(!identity.ok)throw Error('Offline controller handshake failed');
 const claim=await identity.json();
 if(claim.mode!==expectedMode||claim.controller_nonce!==policy.controller_nonce)throw Error('Not the bound controller');
 const delivery=policy.delivery_protocol??'submit_tool_only_v1';
 if(!['submit_tool_only_v1',DELIVERY_V2].includes(delivery)||(delivery===DELIVERY_V2&&claim.delivery_protocol!==delivery))throw Error('Delivery protocol binding drift');
 if(policy.mode==='technical_probe'&&claim.profile_binding_sha256!==policy.profile_binding_sha256)throw Error('Technical profile binding drift');
 if(['study_replay','scored_trial'].includes(policy.mode)){
  if(!/^[a-f0-9]{64}$/.test(policy.study_plan_sha256??'')||!/^t[0-9]{2}$/.test(policy.trial_id??'')||claim.study_plan_sha256!==policy.study_plan_sha256||claim.trial_id!==policy.trial_id||claim.profile_binding_sha256!==policy.profile_binding_sha256)throw Error('Frozen study/trial/profile binding drift');
 }
 const installed=JSON.parse(readFileSync(new URL('./node_modules/@earendil-works/pi-coding-agent/package.json',import.meta.url),'utf8'));
 if(installed.version!=='0.84.4')throw Error('Pinned Pi package identity drift');
 const agentDir=resolve(runRoot,'pi-state');mkdirSync(agentDir,{recursive:false});
 writeFileSync(resolve(agentDir,'auth.json'),'{}\n',{flag:'wx',mode:0o600});
 const runtime=await ModelRuntime.create({authPath:resolve(agentDir,'auth.json'),modelsPath:null,modelsStorePath:resolve(agentDir,'models-cache.json'),allowModelNetwork:false,refreshOnCreate:false});
 runtime.registerProvider('writing-workflow',{
  api:'openai-completions',baseUrl:gateway+'/v1',apiKey:'offline-controller-fixture',authHeader:false,
  models:[{id:policy.model,name:policy.model,reasoning:true,input:['text'],...limits,
   cost:{input:0,output:0,cacheRead:0,cacheWrite:0},
   compat:{supportsStore:false,supportsDeveloperRole:false,supportsReasoningEffort:false,supportsUsageInStreaming:true,supportsStrictMode:false,maxTokensField:'max_completion_tokens',requiresThinkingAsText:false,requiresToolResultName:true}}],
 });
 const model=runtime.getModel('writing-workflow',policy.model);if(!model)throw Error('Bound model is unavailable');
 const loader={getExtensions:()=>({extensions:[],errors:[],runtime:createExtensionRuntime()}),getSkills:()=>({skills:[],diagnostics:[]}),getPrompts:()=>({prompts:[],diagnostics:[]}),getThemes:()=>({themes:[],diagnostics:[]}),getAgentsFiles:()=>({agentsFiles:[]}),getSystemPrompt:()=>policy.messages[0].content,getSystemPromptSource:()=>undefined,getAppendSystemPrompt:()=>[],getAppendSystemPromptSources:()=>[],extendResources:()=>{},reload:async()=>{}};
 let session;let submitted=false;const events=[];
 const customTools=TOOL_NAMES.map(name=>({name,label:name,description:name==='submit_article'?'Submit the final German article and end this trial.':`Bounded ${name} operation on this trial's supplied documents or own notes.`,parameters:{type:'object',additionalProperties:false,properties:schemas[name],required:required[name]},
  async execute(_id,params){
   const r=await fetch(gateway+'/tool/'+name,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(params),redirect:'error'});
   if(!r.ok)throw Error('Bounded controller tool rejected request');
   const result=await r.json();
   if(name==='submit_article'&&result.accepted){submitted=true;void session.abort();}
   return {content:[{type:'text',text:JSON.stringify(result)}],details:result};
  }}));
 ({session}=await createAgentSession({cwd:workspace,agentDir,model,thinkingLevel:'high',modelRuntime:runtime,resourceLoader:loader,
  noTools:'builtin',tools:TOOL_NAMES,customTools,sessionManager:SessionManager.inMemory(workspace),settingsManager:SettingsManager.inMemory({compaction:{enabled:false},retry:{enabled:false,provider:{maxRetries:0}},httpIdleTimeoutMs:0})}));
 session.setAutoCompactionEnabled(false);session.setAutoRetryEnabled(false);
 // Pi's provider otherwise subtracts an estimated prompt and a4096-token
 // reserve. The bound controller has the actual renderer/tokenizer and owns
 // this admission decision. Keep all other provider payload fields intact.
 const originalPayloadHook=session.agent.onPayload;
 session.agent.onPayload=async(payload,selectedModel)=>{
  const prior=(await originalPayloadHook?.(payload,selectedModel))??payload;
  const controlled={...prior,max_completion_tokens:limits.maxTokens};
  delete controlled.max_tokens;
  return controlled;
 };
 session.subscribe(e=>events.push(e));
 let error;let finalDelivery;
 try{
  await session.prompt(policy.messages[1].content+'\n\n'+policy.control_prompt);
  if(!submitted&&delivery===DELIVERY_V2){
   const final=regularFinalResponse(events);
   if(!final)throw Error('Pi did not end with a regular final text');
   const response=await fetch(gateway+'/final-response',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(final),redirect:'error'});
   if(!response.ok)throw Error('Controller rejected regular final text');
   finalDelivery=await response.json();
   if(!finalDelivery.accepted||finalDelivery.delivery_kind!=='assistant_final_text')throw Error('Missing final delivery receipt');
  }
 }
 catch(e){if(!submitted)error={type:e?.constructor?.name??'Error',message:String(e.message)};}
 finally{session.dispose();}
 const delivered=submitted||!!finalDelivery;
 const record={mode:policy.mode,study_plan_sha256:policy.study_plan_sha256,trial_id:policy.trial_id,delivery_protocol:delivery,delivered,delivery_kind:submitted?'submit_article':finalDelivery?.delivery_kind,final_delivery:finalDelivery,pi_version:installed.version,model_limits:limits,output_admission:'bound_controller',active_tools:TOOL_NAMES,discovered_resources:false,automatic_compaction:false,automatic_retry:false,provider_retries:0,http_idle_timeout_ms:0,submitted,error,events};
 writeFileSync(resolve(agentDir,'pi-events.json'),JSON.stringify(record,null,2)+'\n',{flag:'wx',mode:0o600});
 if(!delivered)throw Error('Pi did not deliver an accepted final article');
 return record;
}

if(process.argv[1]&&pathToFileURL(resolve(process.argv[1])).href===import.meta.url){
 const policy=JSON.parse(readFileSync(process.argv[2],'utf8'));
 run(policy).then(result=>{process.stdout.write(JSON.stringify({submitted:result.submitted,delivered:result.delivered,delivery_kind:result.delivery_kind,mode:result.mode})+'\n');},error=>{process.stderr.write(String(error)+'\n');process.exitCode=1;});
}
