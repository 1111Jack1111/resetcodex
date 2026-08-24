const el=id=>document.getElementById(id);
const DATA_URL='./data/status.json';
const zhTime=value=>value?new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value)):'暂无';
function render(data){
  const pulse=el('pulse');pulse.className='pulse';
  if(data.status==='confirmed_reset')pulse.classList.add('window');
  else if(data.status==='confirmed_upcoming'||data.status==='prediction')pulse.classList.add('verify');
  else pulse.classList.add('stale');
  el('status-label').textContent=data.label||'无新信号';
  el('headline').textContent=data.headline||'等待下一次可靠消息';
  el('last-updated').textContent=zhTime(data.checked_at);
  el('confidence-value').textContent=data.confidence?`${data.confidence}%`:'—';
  el('meter').style.width=`${Math.max(0,Math.min(100,data.confidence||0))}%`;
  el('reason').textContent=data.reason||'没有新的可靠信号。';
  el('signal-source').href=data.source_url||'https://x.com/thsottiaux';
  el('signal-source-name').textContent=data.source_name||'Tibo 公开消息';
  el('signal-time').textContent=data.signal_at?`${zhTime(data.signal_at)} · ${data.source_verified?'官方接口已核验':'辅助信号'}`:'暂无近期信号';
  const openai=data.openai_status?.description||'暂时无法读取';
  el('signal-source-note').textContent=`OpenAI 状态：${openai}。${data.source_health==='partial'?'部分公开来源本轮不可用。':'公开来源检查正常。'}`;
  const old=localStorage.getItem('tibo-watch-signal');
  if(data.signal_id&&old&&old!==data.signal_id&&localStorage.getItem('tibo-watch-notice')==='on'&&Notification.permission==='granted')new Notification('发现新的额度重置信号',{body:data.headline});
  if(data.signal_id)localStorage.setItem('tibo-watch-signal',data.signal_id);
}
async function refresh(showResult=false){
  const box=el('result');
  if(showResult){box.classList.remove('hidden');box.innerHTML='<strong>正在读取最新公开结果…</strong><p>不会发送账号或设备信息。</p>'}
  try{
    const response=await fetch(`${DATA_URL}?t=${Date.now()}`,{cache:'no-store'});
    if(!response.ok)throw new Error('status');
    const data=await response.json();render(data);
    if(showResult)box.innerHTML=`<strong>${data.label} · ${zhTime(data.checked_at)}</strong><p>${data.reason} 请到 Usage 页面确认个人账户是否实际到账。</p>`;
  }catch{
    if(showResult)box.innerHTML='<strong>暂时无法读取自动检查结果</strong><p>可能正在部署或网络受限，请稍后再试。</p>';
  }
}
refresh();setInterval(()=>refresh(false),300000);
const notify=el('notify');let enabled=localStorage.getItem('tibo-watch-notice')==='on';
function paintNotice(){notify.querySelector('i').classList.toggle('on',enabled);notify.querySelector('b').textContent=enabled?'已开':'关闭'}
paintNotice();notify.onclick=async()=>{if(!enabled&&'Notification'in window&&Notification.permission==='default')await Notification.requestPermission();enabled=!enabled;localStorage.setItem('tibo-watch-notice',enabled?'on':'off');paintNotice()};
el('check').onclick=async function(){this.disabled=true;await refresh(true);this.disabled=false};
if('serviceWorker'in navigator)navigator.serviceWorker.register('./sw.js').catch(()=>{});
