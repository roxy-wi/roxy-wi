document.addEventListener('DOMContentLoaded',()=>{
    const root=document.getElementById('proxy-diagnostics');if(!root)return;
    const el=id=>document.getElementById('diagnostics-'+id),node=(tag,text)=>{const result=document.createElement(tag);if(text!==undefined)result.textContent=text;return result;};
    let servers=[],timer,version=0;
    const labels={'configuration':'Configuration sources','frontend':'Frontend','dns-controller':'DNS (controller)','dns-proxy-host':'DNS (proxy host)','vip':'VIP / destination','proxy-listener':'Proxy listener','tcp':'TCP','tls-sni':'TLS / SNI','http':'HTTP response','backends':'Candidate backends'};
    const message=text=>{el('message').textContent=text;};
    async function api(url,data){try{return await jQuery.ajax({url,method:data===undefined?'GET':'POST',contentType:'application/json',global:false,data:data===undefined?undefined:JSON.stringify(data)});}catch(error){throw new Error(error.responseJSON?.error||'Diagnostic request failed');}}
    function select(input,values,first){const old=input.value;input.replaceChildren(...(first?[new Option(first,'')]:[]),...values.map(v=>new Option(v.name,v.id)));if(values.some(v=>String(v.id)===old))input.value=old;if(jQuery(input).selectmenu('instance'))jQuery(input).selectmenu('refresh');else jQuery(input).selectmenu();}
    function busy(value){if(el('run'))el('run').disabled=value;}
    function display(item){const report=item.report;el('stages').replaceChildren();el('summary').textContent=report?.summary||'No completed assessment selected';el('time').textContent=report?new Date(report.observed_at).toLocaleString()+' · '+report.url:'';
        if(!report)return;select(el('frontend'),report.frontends.map(f=>({id:f.id,name:f.name})),'Choose automatically when unambiguous');
        report.stages.forEach(stage=>{const row=node('tr'),evidence=node('td',stage.message),details=node('details');details.append(node('summary','Observed details'),node('pre',JSON.stringify(stage.details,null,2)));evidence.append(details);row.append(node('td',labels[stage.key]||stage.key),node('td',stage.state),evidence);el('stages').append(row);});}
    async function poll(id,generation){try{const data=await api(root.dataset.assessments.replace(/\/0$/,'/'+id));if(generation!==version)return;const item=data.data;
        if(['created','published','running'].includes(item.status)){busy(true);message('Assessment queued/running in Operations.');timer=setTimeout(()=>poll(id,generation),2000);return;}
        busy(false);message(item.error||'');display(item);await history(false);
    }catch(error){if(generation===version){busy(false);message(error.message);}}}
    async function history(update=true){clearTimeout(timer);if(!el('server').value)return;const generation=version;
        try{const data=await api(root.dataset.api+'?'+new URLSearchParams({service:el('service').value,server_id:el('server').value}));if(generation!==version)return;
            el('history').replaceChildren();data.data.forEach(item=>{const button=node('button',`#${item.id} · ${new Date(item.created_at).toLocaleString()} · ${item.status}`);button.type='button';button.className='rw-button rw-button-secondary';button.addEventListener('click',()=>display(item));el('history').append(button);});
            if(update)display(data.data.find(item=>item.report)||{});const pending=data.data.find(item=>['created','published','running'].includes(item.status));busy(Boolean(pending));if(pending)poll(pending.id,generation);
        }catch(error){message(error.message);}}
    function chooseServer(){version++;clearTimeout(timer);busy(false);select(el('server'),servers.filter(s=>s.services.includes(el('service').value)).map(s=>({id:s.id,name:s.name+' ('+s.ip+')'})),'Select server');select(el('frontend'),[],'Choose automatically when unambiguous');display({});}
    el('service').addEventListener('change',chooseServer);jQuery(el('service')).selectmenu({change:chooseServer});
    function serverChanged(){version++;clearTimeout(timer);select(el('frontend'),[],'Choose automatically when unambiguous');history();}
    el('server').addEventListener('change',serverChanged);jQuery(el('server')).selectmenu({change:serverChanged});el('refresh').addEventListener('click',()=>history());
    el('form').addEventListener('submit',async event=>{event.preventDefault();if(!el('server').value)return;const generation=++version;clearTimeout(timer);busy(true);
        try{const data=await api(root.dataset.api,{service:el('service').value,server_id:Number(el('server').value),url:el('url').value,frontend_id:el('frontend').value||null});if(generation===version)poll(data.id,generation);}catch(error){busy(false);message(error.message);}});
    api(root.dataset.choices).then(data=>{servers=data.servers;select(el('service'),data.services.map(name=>({id:name,name:name==='haproxy'?'HAProxy':name==='nginx'?'NGINX':'Apache'})));const wanted=new URLSearchParams(window.location.search).get('service');if(data.services.includes(wanted)){el('service').value=wanted;jQuery(el('service')).selectmenu('refresh');}chooseServer();}).catch(error=>message(error.message));
});
