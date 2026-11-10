const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
async function request(url, options={}) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Controlla i dati inseriti');
  return body;
}
async function loadOpere(){
  try {
    const opere = await request('/api/opere?q=' + encodeURIComponent($('searchOpere').value));
    $('opereList').innerHTML = opere.map(o=>`<article class="art-card"><span class="tag">${esc(o.categoria)} · ${esc(o.anno)}</span><h3>${esc(o.titolo)}</h3><p>${esc(o.artista)}</p><a href="${esc(o.url_fonte)}" target="_blank" rel="noopener noreferrer">Scheda ufficiale MoMA ↗</a></article>`).join('') || '<p>Nessun risultato per la ricerca.</p>';
  } catch(e){$('opereList').textContent = e.message;}
}
async function loadEventi(){
  try {
    const eventi = await request('/api/eventi');
    $('eventiList').innerHTML = eventi.map(e=>`<div class="event"><strong>${esc(e.titolo)}</strong><span>${esc(e.data)} · ${esc(e.orario)} · ${e.disponibili} posti disponibili</span><p>${esc(e.descrizione)}</p></div>`).join('');
    $('eventoId').innerHTML = eventi.map(e=>`<option value="${e.id}" ${e.disponibili<1?'disabled':''}>${esc(e.titolo)} (${e.disponibili} posti)</option>`).join('');
  }catch(e){$('eventiList').textContent=e.message;}
}
$('searchOpere').addEventListener('input',loadOpere);
$('prenotaForm').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.target;
  const data={evento_id:Number(form.evento_id.value),nome:form.nome.value,email:form.email.value,persone:Number(form.persone.value)};
  try{const result=await request('/api/prenotazioni',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    $('prenotaEsito').textContent=`Prenotazione dimostrativa n. ${result.id} confermata per ${result.persone} persona/e.`;form.reset();await loadEventi();}
  catch(e){$('prenotaEsito').textContent='Errore: '+e.message;}
});
$('feedbackForm').addEventListener('submit',async event=>{
  event.preventDefault();try{await request('/api/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({voto:Number($('voto').value),commento:$('commento').value})});$('feedbackEsito').textContent='Feedback di prova registrato.';$('commento').value='';}
  catch(e){$('feedbackEsito').textContent='Errore: '+e.message;}
});
$('adminForm').addEventListener('submit',async event=>{
  event.preventDefault();const headers={'X-Admin-Key':$('adminKey').value};
  try{const [stats,rows]=await Promise.all([request('/api/admin/dashboard',{headers}),request('/api/admin/prenotazioni',{headers})]);
    $('adminData').hidden=false;
    $('stats').innerHTML=[['Prenotazioni',stats.prenotazioni_confermate],['Persone',stats.persone_prenotate],['Eventi',stats.eventi],['Voto medio',stats.voto_medio??'—']].map(([label,value])=>`<div class="stat"><strong>${esc(value)}</strong><span>${esc(label)}</span></div>`).join('');
    $('adminRows').innerHTML=rows.map(r=>`<tr><td>${r.id}</td><td>${esc(r.nome)}</td><td>${esc(r.evento)}</td><td>${r.persone}</td><td>${esc(r.stato)}</td></tr>`).join('')||'<tr><td colspan="5">Nessuna prenotazione</td></tr>';
  }catch(e){$('adminData').hidden=true;alert(e.message);}
});
loadOpere();loadEventi();
