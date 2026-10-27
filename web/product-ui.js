/* Product navigation, progressive controls, and a predictable creation workflow. */
(() => {
  'use strict';
  const paths = {
    studio:'M4 6h16M4 12h10M4 18h7M18 11v9m-3-3 3 3 3-3',
    voices:'M8 10V7a4 4 0 0 1 8 0v3m-4-7v18M5 9v6m14-6v6M2 11v2m20-2v2M8 16a4 4 0 0 0 8 0',
    projects:'M3 7a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z',
    batch:'M8 5h13M8 12h13M8 19h13M3 5h.01M3 12h.01M3 19h.01',
    longform:'M4 3h12l4 4v14H4V3Zm12 0v5h4M8 12h8M8 16h6',
    tasks:'M12 8v4l3 2M21 12a9 9 0 1 1-2.6-6.4M18 3v5h5',
    review:'M4 8v8m4-11v14m4-11v8m4-13v18m4-14v10',
    exports:'M12 3v12m-4-4 4 4 4-4M4 15v5h16v-5',
    assets:'M4 7h16M9 3h6l1 4H8l1-4Zm-3 4 1 14h10l1-14M10 11v6m4-6v6',
    settings:'M4 6h16M4 12h16M4 18h16M8 3v6m8 0v6M10 15v6',
    search:'m21 21-4.5-4.5M18 10.5a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0Z',
    menu:'M4 6h16M4 12h16M4 18h16', close:'m6 6 12 12M6 18 18 6',
    chevron:'m9 6 6 6-6 6', arrow:'M4 12h16m-5-5 5 5-5 5',
    mark:'M4 12v1m4-6v11m4-14v16m4-13v11m4-7v3',
    upload:'M12 16V4m-4 4 4-4 4 4M4 15v5h16v-5',
    language:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM3 12h18M12 3c-5 5-5 13 0 18M12 3c5 5 5 13 0 18',
    theme:'M12 3v2m0 14v2M3 12h2m14 0h2M5.6 5.6 7 7m10 10 1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z'
  };
  const icon = name => `<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name] || paths.mark}"/></svg>`;
  const sidebar=document.querySelector('.sidebar'), main=document.querySelector('main'), header=main.querySelector('header');
  const nav=sidebar.querySelector('nav'), navItems=[...nav.querySelectorAll('.nav')];
  sidebar.id='workspace-navigation';
  const brand=sidebar.querySelector('.brand-icon'); brand.innerHTML=icon('mark'); brand.setAttribute('aria-hidden','true');
  const skip=document.createElement('a');skip.className='skip-link';skip.href='#workspace-content';skip.textContent=tr('跳到主要内容');document.body.prepend(skip);
  document.querySelector('.content').id='workspace-content';
  skip.onclick=event=>{event.preventDefault();const heading=document.querySelector('.page.active h1');if(heading){heading.tabIndex=-1;heading.focus();}};
  for(const button of navItems){
    button.querySelector('span').innerHTML=icon(button.dataset.page);
    button.removeAttribute('title');
  }
  for(const [label,pages] of [['创作',['studio','voices','batch','longform']],['制作',['tasks','review','exports']],['资源',['projects','assets','settings']]]){
    const group=document.createElement('div');group.className='nav-group';
    const title=document.createElement('span');title.className='nav-group-label';title.textContent=tr(label);group.append(title);
    for(const page of pages){const button=navItems.find(item=>item.dataset.page===page);if(button)group.append(button);}
    nav.append(group);
  }
  const menu=document.createElement('button');menu.type='button';menu.className='icon-btn menu-toggle';menu.innerHTML=icon('menu');menu.setAttribute('aria-label',tr('打开工作区导航'));menu.setAttribute('aria-controls',sidebar.id);menu.setAttribute('aria-expanded','false');header.prepend(menu);
  const close=document.createElement('button');close.type='button';close.className='icon-btn drawer-close';close.innerHTML=icon('close');close.setAttribute('aria-label',tr('关闭导航'));sidebar.prepend(close);
  const backdrop=document.createElement('button');backdrop.type='button';backdrop.className='nav-backdrop';backdrop.hidden=true;backdrop.tabIndex=-1;backdrop.setAttribute('aria-label',tr('关闭导航'));document.body.append(backdrop);
  const compact=matchMedia('(max-width:1000px)');
  function closeMenu(returnFocus=false){delete document.body.dataset.navOpen;backdrop.hidden=true;menu.setAttribute('aria-expanded','false');main.inert=false;sidebar.inert=compact.matches;if(returnFocus)menu.focus();}
  function openMenu(){if(!compact.matches)return;sidebar.inert=false;document.body.dataset.navOpen='true';backdrop.hidden=false;menu.setAttribute('aria-expanded','true');main.inert=true;requestAnimationFrame(()=>{if(document.body.hasAttribute('data-nav-open'))close.focus();});}
  menu.onclick=openMenu;close.onclick=()=>closeMenu(true);backdrop.onclick=()=>closeMenu(true);
  for(const [id,name] of [['ui-language','language'],['theme-mode','theme']]){
    const label=$(id).closest('label');label.insertAdjacentHTML('afterbegin',icon(name));label.title=tr($(id).getAttribute('aria-label'));
  }
  compact.addEventListener('change',()=>closeMenu());closeMenu();
  document.addEventListener('keydown',event=>{
    if(!document.body.hasAttribute('data-nav-open'))return;
    if(event.key==='Escape'){event.preventDefault();closeMenu(true);return;}
    if(event.key==='Tab'){
      const items=[...sidebar.querySelectorAll('button:not(:disabled),a[href],select')].filter(el=>el.getClientRects().length);
      const first=items[0],last=items.at(-1);
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
    }
  });

  // Text -> voice -> submit: keep the controls in one native form at every width.
  const grid=document.querySelector('#page-studio .studio-grid'), form=$('generate-form');
  const editor=grid.querySelector('.editor-panel'), stack=grid.querySelector('.stack'), footer=form.querySelector('.generate-footer');
  const fields=[...form.children].filter(child=>child!==footer);
  form.remove();editor.append(...fields);grid.replaceWith(form);form.classList.add('studio-grid');footer.classList.add('studio-submitbar');form.append(editor,stack,footer);
  const generate=$('generate-button');generate.insertAdjacentHTML('beforeend',icon('arrow'));
  for(const button of form.querySelectorAll('button'))if(button!==generate&&!button.hasAttribute('type'))button.type='button';
  const genText=$('gen-text');genText.setAttribute('aria-label',tr('配音内容'));genText.spellcheck=false;
  const shortcuts=form.querySelector('.workflow-shortcuts');if(shortcuts)form.before(shortcuts);
  const optionPanel=$('gen-candidates').closest('.panel'), optionTitle=optionPanel.querySelector('h2');
  const options=document.createElement('details');options.className='panel generation-options';
  const optionSummary=document.createElement('summary');optionSummary.textContent=tr('生成选项');
  optionTitle.remove();options.append(optionSummary,...optionPanel.childNodes);optionPanel.replaceWith(options);
  const refGeneration=document.querySelector('.reference-generation');
  const refDetails=document.createElement('details');refDetails.className='reference-options';
  const refSummary=document.createElement('summary');refSummary.textContent=tr('参考与克隆');
  refGeneration.before(refDetails);refDetails.append(refSummary,refGeneration);
  function updateReferenceVisibility(){
    refDetails.hidden=!state.references.length;
    if($('gen-reference').value||$('gen-clone-mode').value==='hifi')refDetails.open=true;
  }
  updateReferenceVisibility();
  document.addEventListener('change',event=>{if(['gen-voice','gen-reference','gen-clone-mode'].includes(event.target.id))updateReferenceVisibility();});
  for(const zone of document.querySelectorAll('.drop-zone'))zone.insertAdjacentHTML('afterbegin',icon('upload'));
  const uploadButton=$('reference-form').querySelector('button[type=submit]');uploadButton.classList.remove('secondary');uploadButton.classList.add('primary');

  const projectPanel=$('project-form').closest('.panel'),projectCreate=document.createElement('details');
  projectCreate.className='panel project-create';projectCreate.open=!state.projects.length;
  const projectSummary=document.createElement('summary');projectSummary.textContent=tr('创建项目');
  projectCreate.append(projectSummary,...projectPanel.childNodes);projectPanel.replaceWith(projectCreate);
  let projectInitialRender=false;const priorProjectRender=renderProjects;renderProjects=function(){priorProjectRender();if(!projectInitialRender){projectInitialRender=true;if(state.projects.length&&!$('project-form').dataset.dirty)projectCreate.open=false;}};
  document.addEventListener('workflow-form-success',event=>{if(event.target.id==='project-form')projectCreate.open=false;});
  const libraryActions=$('library-actions'),newVoice=$('new-voice');
  newVoice.classList.remove('primary');newVoice.classList.add('secondary');
  const libraryManagement=document.querySelector('[data-assets-open="voices"]');if(libraryManagement)libraryActions.append(libraryManagement);
  const fromRecording=document.querySelector('#voice-pane-library .workspace-intro [data-voice-pane="quick"]');
  if(fromRecording){fromRecording.classList.remove('secondary');fromRecording.classList.add('primary');}
  document.querySelector('.review-export-bridge .toolbar').prepend($('compare-selected'));
  const runtimeDetails=document.createElement('details');runtimeDetails.className='runtime-details';
  const runtimeSummary=document.createElement('summary');runtimeSummary.textContent=tr('安装路径与运行环境');
  $('system-info').before(runtimeDetails);runtimeDetails.append(runtimeSummary,$('system-info'));
  const originalSettings=renderSettings;
  renderSettings=async function(){
    await originalSettings();
    for(const metadata of document.querySelectorAll('.model-card>p.hint')){
      const details=document.createElement('details');details.className='model-metadata';
      const summary=document.createElement('summary');summary.textContent=tr('支持语言与模型版本');
      metadata.before(details);details.append(summary,metadata);
    }
  };
  const selectionDock=document.createElement('div');selectionDock.className='selection-dock';selectionDock.hidden=true;
  const dockCount=document.createElement('span');dockCount.setAttribute('role','status');
  const dockAction=document.createElement('button');dockAction.type='button';dockAction.className='primary';
  const dockClear=document.createElement('button');dockClear.type='button';dockClear.className='icon-btn';dockClear.innerHTML=icon('close');dockClear.setAttribute('aria-label',tr('清空选择'));
  selectionDock.append(dockCount,dockAction,dockClear);document.body.append(selectionDock);
  function syncSelectionDock(){
    if(state.page!=='review'){selectionDock.hidden=true;document.body.classList.remove('has-selection-dock');return;}
    const items=state.selected.size?state.results.filter(result=>state.selected.has(result.id)):[];
    selectionDock.hidden=state.page!=='review'||!items.length;
    document.body.classList.toggle('has-selection-dock',!selectionDock.hidden);
    const count=tr('已选择 {0} 个结果',[items.length]);if(dockCount.textContent!==count)dockCount.textContent=count;
    const approved=items.length&&items.every(item=>item.review==='approved');
    dockAction.textContent=tr(approved?'导出所选已审核音频':'审核所选');
    dockAction.disabled=approved?$('review-export-now').disabled:$('review-batch-approve').disabled;
    dockAction.onclick=()=>$(approved?'review-export-now':'review-batch-approve').click();
  }
  dockClear.onclick=()=>{$('review-clear-selected').click();syncSelectionDock();document.querySelector('#page-review h1').focus({preventScroll:true});};
  document.addEventListener('change',syncSelectionDock);
  document.addEventListener('click',()=>queueMicrotask(syncSelectionDock));

  // A small workflow map gives the task/review/export pages a shared location.
  const steps=[['studio','语音生成'],['tasks','任务队列'],['review','试听与审核'],['exports','导出中心']];
  const productionPath=document.createElement('div');productionPath.className='production-path';productionPath.setAttribute('role','navigation');productionPath.setAttribute('aria-label',tr('制作流程'));
  steps.forEach(([page,label],index)=>{
    if(index){const arrow=document.createElement('span');arrow.className='path-chevron';arrow.innerHTML=icon('chevron');productionPath.append(arrow);}
    const button=document.createElement('button');button.type='button';button.dataset.stage=page;button.innerHTML=icon(page)+`<span>${e(tr(label))}</span>`;button.onclick=()=>navigate(page);productionPath.append(button);
  });
  function updatePath(){
    const heading=document.querySelector('.page.active .page-heading>div');
    const visible=steps.some(([page])=>page===state.page);
    productionPath.hidden=!visible;
    if(visible&&heading)heading.append(productionPath);
    for(const button of productionPath.querySelectorAll('button')){
      if(button.dataset.stage===state.page)button.setAttribute('aria-current','step');else button.removeAttribute('aria-current');
    }
  }
  updatePath();

  // Keyboard workspace switcher, using the same routes as the sidebar.
  const jump=document.createElement('button');jump.type='button';jump.className='jump-button';jump.innerHTML=icon('search')+`<span class="jump-label">${e(tr('跳转'))}</span><kbd>Ctrl K</kbd>`;jump.setAttribute('aria-label',tr('跳转工作区'));header.querySelector('.header-right').prepend(jump);
  const dialog=document.createElement('dialog');dialog.className='jump-dialog';dialog.setAttribute('aria-labelledby','jump-title');
  dialog.innerHTML=`<h2 id="jump-title">${e(tr('跳转工作区'))}</h2><input id="jump-search" autocomplete="off" placeholder="${e(tr('搜索工作区'))}" aria-label="${e(tr('搜索工作区'))}"><div class="jump-results"></div><footer>${e(tr('方向键选择 · Enter 打开 · Esc 关闭'))}</footer>`;
  document.body.append(dialog);const search=dialog.querySelector('input'),jumpResults=dialog.querySelector('.jump-results');let jumpOrigin;
  function renderJump(){
    jumpResults.replaceChildren();const value=search.value.trim().toLocaleLowerCase();
    for(const item of navItems){
      const label=item.querySelector('span:nth-child(2)')?.textContent||item.innerText;
      if(value&&!label.toLocaleLowerCase().includes(value))continue;
      const button=document.createElement('button');button.type='button';button.innerHTML=icon(item.dataset.page)+`<span>${e(label)}</span>`;
      button.onclick=()=>{dialog.close();navigate(item.dataset.page);};jumpResults.append(button);
    }
    if(value)for(const [key,pane,aliases] of [['参考片段库','references','reference clips 参考 参照 참조'],['人物音色库','library','voice library 人物 音色 목소리'],['文字设计声音','design','voice design 声音设计 音声設計 디자인'],['按人物整理','processing','speakers tracking 人物分离 話者 화자']]){
      const label=tr(key);if(!(label+' '+aliases).toLocaleLowerCase().includes(value))continue;const button=document.createElement('button');button.type='button';button.innerHTML=icon('voices')+`<span>${e(label)}</span>`;button.onclick=()=>{dialog.close();navigate('voices');window.voiceWorkspace.showPane(pane);};jumpResults.append(button);
    }
    if(!jumpResults.children.length){const message=document.createElement('p');message.className='empty';message.textContent=tr('没有匹配的工作区');jumpResults.append(message);}
  }
  function openJump(){jumpOrigin=compact.matches&&sidebar.contains(document.activeElement)?menu:document.activeElement===document.body?(compact.matches?menu:jump):document.activeElement;closeMenu();search.value='';renderJump();dialog.showModal();search.focus();}
  jump.onclick=openJump;search.addEventListener('input',renderJump);
  dialog.addEventListener('close',()=>requestAnimationFrame(()=>{const active=document.activeElement;if((active===document.body||active===dialog||(compact.matches&&sidebar.contains(active)))&&jumpOrigin?.isConnected)jumpOrigin.focus();}));
  dialog.addEventListener('click',event=>{if(event.target===dialog){const box=dialog.getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)dialog.close();}});
  dialog.addEventListener('keydown',event=>{
    if(event.key==='Escape'){event.preventDefault();dialog.close();jumpOrigin?.focus();return;}
    const buttons=[...jumpResults.querySelectorAll('button')];
    if(event.key==='ArrowDown'||event.key==='ArrowUp'){
      event.preventDefault();const current=buttons.indexOf(document.activeElement),delta=event.key==='ArrowDown'?1:-1;
      const next=current<0?(delta>0?0:buttons.length-1):(current+delta+buttons.length)%buttons.length;
      buttons[next]?.focus();
    }else if(event.key==='Enter'&&document.activeElement===search){event.preventDefault();buttons[0]?.click();}
  });
  document.addEventListener('keydown',event=>{
    if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();if(!document.querySelector('dialog[open]'))openJump();}
    if((event.ctrlKey||event.metaKey)&&event.key==='Enter'&&state.page==='studio'&&!dialog.open&&!document.querySelector('dialog[open]')&&!form.dataset.pending){event.preventDefault();form.requestSubmit(generate);}
    if(event.defaultPrevented)return;
    const tab=event.target.closest?.('[role=tab]'),list=tab?.closest('[role=tablist]');
    if(list&&['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){
      const tabs=[...list.querySelectorAll('[role=tab]')].filter(el=>!el.disabled);let index=tabs.indexOf(tab);
      index=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
      event.preventDefault();tabs[index]?.click();tabs[index]?.focus();
    }
  });
  function decorateEmpty(){
    for(const element of document.querySelectorAll('.page.active .empty:not([data-product-empty])')){
      element.dataset.productEmpty='true';const graphic=document.createElement('span');graphic.className='empty-icon';graphic.innerHTML=icon(state.page);element.prepend(graphic);
      let label,run;
      if(state.page==='voices'&&element.closest('#voice-list')){label='从录音创建音色';run=()=>window.voiceWorkspace.showPane('quick');}
      else if(state.page==='review'){label='开始配音';run=()=>navigate('studio');}
      else if(state.page==='exports'){label='返回试听与审核';run=()=>navigate('review');}
      else if(state.page==='projects'){label='创建项目';run=()=>{projectCreate.open=true;$('project-name').focus();};}
      else if(state.page==='tasks'){label='开始配音';run=()=>navigate('studio');}
      if(label){const button=document.createElement('button');button.type='button';button.className='secondary empty-action';button.textContent=tr(label);button.onclick=run;element.append(button);}
    }
  }
  window.addEventListener('voice-page-change',()=>{const wasOpen=document.body.hasAttribute('data-nav-open');closeMenu();if(wasOpen)document.querySelector('.page.active h1')?.focus({preventScroll:true});updatePath();decorateEmpty();syncSelectionDock();});
  function refreshTabs(){for(const list of document.querySelectorAll('[role=tablist]'))for(const tab of list.querySelectorAll('[role=tab]'))tab.tabIndex=tab.getAttribute('aria-selected')==='true'?0:-1;}
  document.addEventListener('click',event=>{if(event.target.closest?.('[role=tab]'))refreshTabs();});
  window.addEventListener('voice-context-change',refreshTabs);refreshTabs();
  window.addEventListener('voice-data-ready',()=>{updateReferenceVisibility();decorateEmpty();syncSelectionDock();});
  document.addEventListener('workflow-form-settled',decorateEmpty);
  decorateEmpty();
})();
