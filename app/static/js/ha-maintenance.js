document.addEventListener('DOMContentLoaded',()=>{
    const root=document.getElementById('ha-maintenance');if(!root)return;
    const el=id=>document.getElementById(id),node=(tag,text)=>{const result=document.createElement(tag);if(text!==undefined)result.textContent=text;return result;};
    let timer,selection=0,requestedChange=Number(new URLSearchParams(window.location.search).get('change'))||null;
    const message=text=>{el('ha-maintenance-message').textContent=text;};
    async function api(url,data){try{return await jQuery.ajax({url,method:data===undefined?'GET':'POST',contentType:'application/json',data:data===undefined?undefined:JSON.stringify(data),global:false});}catch(error){throw new Error(error.responseJSON?.error||'Maintenance request failed');}}
    function select(input,values){input.replaceChildren(new Option('Select',''),...values.map(value=>new Option(value.name,value.id)));if(jQuery(input).selectmenu('instance'))jQuery(input).selectmenu('refresh');else jQuery(input).selectmenu();}
    async function members(){const value=el('maintenance-cluster').value,version=++selection;if(!value){select(el('maintenance-node'),[]);return;}try{const data=await api(root.dataset.subjects+'/'+value);if(version!==selection)return;select(el('maintenance-node'),data.profile.nodes.filter(n=>!n.name.startsWith('Witness: ')));}catch(error){message(error.message);}}
    async function refresh(){clearTimeout(timer);try{const data=await api(root.dataset.api);el('maintenance-plans').replaceChildren();let pending=false;
        data.data.forEach(plan=>{const panel=node('section');panel.className='rw-panel';panel.dataset.plan=plan.id;
            panel.append(node('h3',`Plan #${plan.id} · ${plan.title}`),node('p',`${plan.cluster_name} · ${plan.provider} · ${plan.node_name}`),node('p',`State: ${plan.status} · Change #${plan.change_id}: ${plan.change_status}`),node('p','Capacity evidence (operator): '+plan.capacity_evidence));
            if(plan.operation){panel.append(node('p',`Operation #${plan.operation.id}: ${plan.operation.status}${plan.operation.error?' · '+plan.operation.error:''}`));pending=true;}
            const actions=node('div');actions.className='rw-table-toolbar';
            const choices={draft:[['review','Review drain']],reviewed:[['review','Refresh drain review'],['drain','Drain approved node']], 'review-failed':[['review','Review drain']],draining:[['verify','Verify drain'],['review-return','Review return']],unknown:[['verify','Verify drain'],['review-return','Review return']],ready:[['review-return','Review return']], 'return-reviewed':[['review-return','Refresh return review'],['resume','Return approved node']]};
            (Number(root.dataset.role)<=3?choices[plan.status]||[]:[]).forEach(([action,label])=>{const button=node('button',label);button.type='button';button.className='rw-button rw-button-secondary';button.disabled=Boolean(plan.operation)||(['drain','resume'].includes(action)&&plan.change_status!=='approved');button.addEventListener('click',async()=>{button.disabled=true;try{await api(root.dataset.api+'/'+plan.id+'/'+action,{});await refresh();}catch(error){message(error.message);button.disabled=false;}});actions.append(button);});
            if(plan.can_cancel && Number(root.dataset.role)<=3){const cancel=node('button','Cancel plan');cancel.type='button';cancel.className='rw-button rw-button-secondary';cancel.addEventListener('click',async()=>{try{await api('/changes/api/'+plan.change_id+'/cancel',{});await refresh();}catch(error){message(error.message);}});actions.append(cancel);}
            const link=node('a','Review/approve in Change Center');link.href='/changes?change='+plan.change_id;link.className='ui-button ui-widget ui-corner-all';actions.append(link);panel.append(actions);
            if(plan.review){const detail=node('details');detail.append(node('summary','Reviewed quorum, placement and identities'),node('pre',JSON.stringify(plan.review,null,2)));panel.append(detail);}
            plan.events.forEach(event=>panel.append(node('p',new Date(event.at).toLocaleString()+' · '+event.state+' · '+event.message)));el('maintenance-plans').append(panel);
            if(requestedChange===plan.change_id){panel.scrollIntoView({block:'start'});requestedChange=null;}
        });if(pending)timer=setTimeout(refresh,3000);
    }catch(error){message(error.message);}}
    el('maintenance-refresh').addEventListener('click',refresh);
    if(el('maintenance-cluster')){api(root.dataset.subjects).then(data=>{select(el('maintenance-cluster'),data.data.map(row=>({id:row.provider+'/'+row.id,name:row.name+' · '+row.provider})));jQuery(el('maintenance-cluster')).selectmenu({change:members});}).catch(error=>message(error.message));el('maintenance-cluster').addEventListener('change',members);}
    el('ha-maintenance-create')?.addEventListener('submit',async event=>{event.preventDefault();const [provider,cluster]=el('maintenance-cluster').value.split('/');try{await api(root.dataset.api,{provider,cluster_id:Number(cluster),server_id:Number(el('maintenance-node').value),title:el('maintenance-title').value,capacity_confirmed:el('maintenance-confirm-capacity').checked,capacity_evidence:el('maintenance-capacity').value});await refresh();}catch(error){message(error.message);}});
    refresh();
});
