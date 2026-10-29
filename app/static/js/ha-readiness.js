/* Existing Roxy-WI controls; render all remote/user text through textContent. */
document.addEventListener('DOMContentLoaded', () => {
    const root=document.querySelector('#ha-readiness'); if(!root)return;
    const $id=id=>document.getElementById(id), role=Number(root.dataset.role);
    let revision=0, reportId=null, timer=null, sequence=0, testRecords=[], dirty=false, editVersion=0, context=null, registration=null;
    const kinds=['hypervisor','power','uplink','storage'];
    const message=text=>{$id('ha-audit-message').textContent=text;};
    const element=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};
    function base(){const value=$id('ha-audit-cluster').value;return value?root.dataset.api+'/'+value:null;}
    async function api(url,body){try{return await jQuery.ajax({url,method:body===undefined?'GET':'POST',contentType:'application/json',global:false,data:body===undefined?undefined:JSON.stringify(body)});}catch(error){throw new Error(error.responseJSON?.error||'Assessment request failed');}}
    function display(item){
        const report=item.report; reportId=report?item.id:null;
        $id('ha-audit-checks').replaceChildren();$id('ha-audit-tests').replaceChildren();
        $id('ha-audit-time').textContent=report?'Observed '+new Date(report.observed_at).toLocaleString():'No completed audit selected.';
        $id('ha-audit-verification').textContent='Last automatically verified HA test: '+(report&&report.last_verified_test?JSON.stringify(report.last_verified_test):'unknown');
        if(!report)return;
        report.checks.forEach(check=>{const row=element('tr');row.append(element('td',check.key));const detail=element('td',check.message), more=element('details');more.append(element('summary','Observed details'),element('pre',JSON.stringify(check.evidence,null,2)));detail.append(more);row.append(detail,element('td',check.state));$id('ha-audit-checks').append(row);});
        testRecords.forEach(test=>{$id('ha-audit-tests').append(element('p',`${test.kind}: ${test.result} · ${new Date(test.tested_at).toLocaleString()} · operator attestation · ${test.fingerprint===report.fingerprint?'matching configuration':'configuration changed'} · ${test.note}`));});
    }
    $id('ha-audit-nodes').addEventListener('input',()=>{dirty=true;editVersion++;});
    async function refresh(){
        clearTimeout(timer);const url=base(), version=++sequence;if(context!==url){context=url;registration=null;dirty=false;editVersion++;}if(!url)return;
        try{const data=await api(url);if(version!==sequence)return;if(registration!==data.profile.registration_key){dirty=false;editVersion++;registration=data.profile.registration_key;}testRecords=data.profile.attestations;
            if(!dirty){revision=data.profile.revision;
            const nodes=$id('ha-audit-nodes');nodes.replaceChildren();data.profile.nodes.forEach(node=>{const section=element('fieldset');section.dataset.server=node.id;section.append(element('legend',node.name));kinds.forEach(kind=>{const field=element('div');field.className='rw-form-field';const label=element('label',kind),input=element('input');input.id=`ha-domain-${node.id}-${kind}`;label.htmlFor=input.id;input.className='form-control';input.maxLength=128;input.dataset.kind=kind;input.value=(data.profile.domains[String(node.id)]||{})[kind]||'';input.disabled=role>2;field.append(label,input);section.append(field);});nodes.append(section);});}
            const history=$id('ha-audit-history');history.replaceChildren();data.assessments.forEach(item=>{const button=element('button',`#${item.id} · ${new Date(item.created_at).toLocaleString()} · ${item.status}`);button.type='button';button.className='rw-button rw-button-secondary';button.addEventListener('click',()=>display(item));history.append(button);});
            const completed=data.assessments.find(item=>item.report);display(completed||{});
            const pending=data.assessments.find(item=>['created','published','running'].includes(item.status));message(pending?'Audit queued or running in Operations.':data.assessments[0]?.error||'');if(pending)timer=setTimeout(refresh,3000);
        }catch(error){message(error.message);}
    }
    $id('ha-audit-cluster').addEventListener('change',refresh);$id('ha-audit-refresh').addEventListener('click',refresh);
    $id('ha-audit-run')?.addEventListener('click',async()=>{if(!base())return;try{await api(base()+'/run',{});await refresh();}catch(error){message(error.message);}});
    $id('ha-audit-domains').addEventListener('submit',async event=>{event.preventDefault();if(!base())return;const domains={};root.querySelectorAll('[data-server]').forEach(node=>{domains[node.dataset.server]={};node.querySelectorAll('[data-kind]').forEach(input=>{domains[node.dataset.server][input.dataset.kind]=input.value;});});const url=base(), savedVersion=editVersion,savedRegistration=registration;try{const result=await api(url+'/profile',{revision,domains,registration_key:registration});if(base()!==url||registration!==savedRegistration)return;revision=result.profile.revision;if(savedVersion===editVersion)dirty=false;await refresh();}catch(error){message(error.message);}});
    $id('ha-audit-attest')?.addEventListener('submit',async event=>{event.preventDefault();if(!base()||!reportId){message('Select a completed audit first.');return;}try{await api(base()+'/attest',{kind:$id('ha-test-kind').value,result:$id('ha-test-result').value,tested_at:new Date($id('ha-test-at').value).toISOString(),note:$id('ha-test-note').value,assessment_id:reportId});await refresh();}catch(error){message(error.message);}});
    api(root.dataset.api).then(data=>{data.data.forEach(row=>{const option=element('option',row.name+' · '+row.provider);option.value=row.provider+'/'+row.id;$id('ha-audit-cluster').append(option);});if(window.jQuery)jQuery($id('ha-audit-cluster')).selectmenu({change:refresh});}).catch(error=>message(error.message));
});
