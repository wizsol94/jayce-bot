document.addEventListener('DOMContentLoaded', () => {
  const statusEl = document.getElementById('status');
  const btn = document.getElementById('btn');
  const info = document.getElementById('info');
  
  function update(data) {
    const running = data.isRunning || false;
    const stats = data.stats || { scans: 0, tokens: 0, screenshots: 0, errors: 0 };
    
    statusEl.textContent = running ? 'RUNNING' : 'STOPPED';
    statusEl.className = 'status ' + (running ? 'running' : 'stopped');
    btn.textContent = running ? 'STOP' : 'START';
    btn.className = running ? 'stop' : 'start';
    
    document.getElementById('scans').textContent = stats.scans;
    document.getElementById('tokens').textContent = stats.tokens;
    document.getElementById('screenshots').textContent = stats.screenshots || 0;
    document.getElementById('errors').textContent = stats.errors;
    
    if (data.lastScan) {
      info.textContent = 'Last: ' + new Date(data.lastScan).toLocaleTimeString();
    }
  }
  
  chrome.runtime.sendMessage({ action: 'status' }, update);
  
  btn.addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: 'status' }, (data) => {
      const action = data.isRunning ? 'stop' : 'start';
      chrome.runtime.sendMessage({ action }, () => {
        setTimeout(() => chrome.runtime.sendMessage({ action: 'status' }, update), 500);
      });
    });
  });
  
  setInterval(() => chrome.runtime.sendMessage({ action: 'status' }, update), 5000);
});
