(() => {
  const root = document.documentElement, lifecycle = new AbortController();
  const forms = [...document.querySelectorAll('[data-hint-settings],[data-transition-settings],[data-dialog-appearance-settings]')];
  const keys = ['pageTransition','transitionDuration','dialogStyle','dialogShadow'];
  const attributes = Object.fromEntries(keys.map(key => [key,root.dataset[key]]));
  const variables = [...root.style].filter(name => /^--(route-|dialog-|theme-preview)/.test(name));
  variables.push('--theme-preview-duration');
  const styles = new Map(variables.map(name => [name,root.style.getPropertyValue(name)]));
  const shell = document.querySelector('.admin-shell'), compact = shell?.classList.contains('admin-menu--compact');
  const restore = () => {
    keys.forEach(key => { if (attributes[key] === undefined) delete root.dataset[key]; else root.dataset[key] = attributes[key]; });
    styles.forEach((value,name) => { if (value) root.style.setProperty(name,value); else root.style.removeProperty(name); });
    shell?.classList.toggle('admin-menu--compact', compact);
    forms.forEach(form => {
      form.reset();
      form.querySelectorAll('[data-color-value]').forEach(output => { output.textContent = output.parentElement.querySelector('input').value.toUpperCase(); });
      form.querySelectorAll('[data-dialog-value]').forEach(input => {
        const name=input.dataset.dialogValue; form.querySelector('[data-dialog-range="'+name+'"]').value=input.value;
        form.querySelector('[data-dialog-output="'+name+'"]').textContent=input.value+' px';
      });
      const duration=form.querySelector('[data-transition-duration-input]');
      if(duration){form.querySelector('[data-transition-duration-range]').value=duration.value;form.querySelector('[data-transition-duration-output]').textContent=duration.value+' ms';}
      form.querySelectorAll('.is-preview-playing,.is-preview-updating,.is-choice-switching').forEach(node=>node.classList.remove('is-preview-playing','is-preview-updating','is-choice-switching'));
    });
  };
  forms.forEach(form => form.querySelector('[data-appearance-cancel]')?.addEventListener('click', () => {
    restore(); window.BakaUI.notifications.notify('已恢复保存的设置。');
  }, { signal:lifecycle.signal }));
  window.addEventListener('pagehide', restore, { signal:lifecycle.signal });
  window.BakaUI.appearance = { restore, destroy(){restore();lifecycle.abort();} };
})();
