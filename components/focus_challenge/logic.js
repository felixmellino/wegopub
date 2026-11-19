/* Pure browser helpers; no app/server globals, and no random challenge generation. */
(function(root){
 const time=value=>Date.parse(value);
 function memoryFrame(a,now){
  const c=a.config, span=c.memory_flash_ms+c.memory_gap_ms;
  const elapsed=now-(time(a.signal_at)-c.memory_length*span);
  const index=Math.floor(elapsed/span);
  return index>=0&&index<c.memory_length&&elapsed%span<c.memory_flash_ms?(a.memory||[])[index]:null;
 }
 function validTaps(taps,c){return Array.isArray(taps)&&taps.length<=c.precision_targets&&taps.every((v,i)=>Number.isInteger(v)&&v>=0&&v<=c.precision_ms&&(!i||v>taps[i-1]));}
 function mergeTaps(saved,cached,c){
  if(!validTaps(cached,c)||cached.length<saved.length||!saved.every((v,i)=>v===cached[i]))return [...saved];
  return [...cached];
 }
 const api={memoryFrame,validTaps,mergeTaps};
 if(typeof module!=='undefined')module.exports=api;else root.FocusLogic=api;
})(typeof window!=='undefined'?window:globalThis);
