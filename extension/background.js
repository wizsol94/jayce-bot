const VPS_URL = 'http://104.236.105.118:5000';
const API_KEY = 'jayce_collector_2026_secret_key';
const SCAN_INTERVAL = 10 * 60 * 1000; // 10 minutes between full rotations

let scanCount = 0;
let tokenCount = 0;
let screenshotCount = 0;
let errorCount = 0;
let lastSourceCounts = { TRENDING: 0, VOL_5M: 0, VOL_1H: 0 };

// Store stats in local storage
function updateStats() {
  chrome.storage.local.set({
    scanCount,
    tokenCount,
    screenshotCount,
    errorCount,
    lastSourceCounts,
    lastUpdate: Date.now()
  });
}

// Heartbeat to VPS
async function sendHeartbeat() {
  try {
    await fetch(`${VPS_URL}/heartbeat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
      body: JSON.stringify({ 
        status: 'alive', 
        scans: scanCount, 
        tokens: tokenCount,
        screenshots: screenshotCount,
        sources: lastSourceCounts
      })
    });
  } catch (e) {
    console.error('Heartbeat failed:', e);
  }
}

// Main scan function - triggers the rotation
async function runScan() {
  console.log('Jayce: Starting WizTheory rotation scan...');
  scanCount++;
  updateStats();
  
  try {
    // Find or create DEX Screener tab with YOUR exact filters
    const mainUrl = 'https://dexscreener.com/?rankBy=trendingScoreH6&order=desc&chainIds=solana&dexIds=pumpswap,pumpfun,raydium&minLiq=10000&minMarketCap=100000&minAge=1&profile=0&launchpads=1';
    
    const tabs = await chrome.tabs.query({ url: '*://dexscreener.com/*' });
    let tab;
    
    if (tabs.length > 0) {
      tab = tabs[0];
      await chrome.tabs.update(tab.id, { url: mainUrl, active: false });
    } else {
      tab = await chrome.tabs.create({ url: mainUrl, active: false });
    }
    
    // Wait for page to load
    await sleep(5000);
    
    // Inject content script
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ['content.js']
    });
    
    await sleep(2000);
    
    // Trigger the rotation scan
    await chrome.tabs.sendMessage(tab.id, { action: 'collectTokens' });
    
  } catch (e) {
    console.error('Scan error:', e);
    errorCount++;
    updateStats();
  }
}

// Handle messages from content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'tokensCollected') {
    handleTokensCollected(message.data, sender.tab);
  }
  sendResponse({ status: 'ok' });
  return true;
});

// Process collected tokens and capture screenshots
async function handleTokensCollected(data, tab) {
  const { tokens, source_counts } = data;
  console.log(`Jayce: Received ${tokens.length} unique tokens from rotation`);
  console.log(`  TRENDING: ${source_counts.TRENDING}`);
  console.log(`  5M VOL: ${source_counts.VOL_5M}`);
  console.log(`  1H VOL: ${source_counts.VOL_1H}`);
  
  tokenCount += tokens.length;
  lastSourceCounts = source_counts;
  updateStats();
  
  // Send tokens to VPS
  try {
    await fetch(`${VPS_URL}/tokens`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
      body: JSON.stringify({ tokens, source_counts })
    });
    console.log('Jayce: Tokens sent to VPS');
  } catch (e) {
    console.error('Failed to send tokens:', e);
    errorCount++;
  }
  
  // Capture screenshots for top tokens from each source
  const screenshotTargets = selectScreenshotTargets(tokens, 25);
  
  for (const token of screenshotTargets) {
    try {
      await chrome.tabs.update(tab.id, { url: token.url });
      await sleep(3500); // Wait for chart to fully load
      
      const screenshot = await chrome.tabs.captureVisibleTab(null, { format: 'png' });
      
      await fetch(`${VPS_URL}/screenshot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': API_KEY },
        body: JSON.stringify({
          pair_address: token.pair_address,
          symbol: token.symbol,
          source: token.source,
          screenshot: screenshot
        })
      });
      
      screenshotCount++;
      console.log(`Jayce: Screenshot ${token.symbol} (${token.source})`);
      
    } catch (e) {
      console.error(`Screenshot error ${token.symbol}:`, e);
      errorCount++;
    }
  }
  
  updateStats();
  console.log('Jayce: Rotation scan complete');
}

// Select tokens for screenshots - balanced across sources
function selectScreenshotTargets(tokens, count) {
  const bySource = {
    TRENDING: tokens.filter(t => t.source === 'TRENDING'),
    VOL_5M: tokens.filter(t => t.source === 'VOL_5M'),
    VOL_1H: tokens.filter(t => t.source === 'VOL_1H')
  };
  
  const selected = [];
  const seen = new Set();
  
  // Take top tokens from each source
  const perSource = Math.ceil(count / 3);
  
  for (const source of ['TRENDING', 'VOL_5M', 'VOL_1H']) {
    let added = 0;
    for (const token of bySource[source]) {
      if (added >= perSource) break;
      if (seen.has(token.pair_address)) continue;
      seen.add(token.pair_address);
      selected.push(token);
      added++;
    }
  }
  
  return selected.slice(0, count);
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Start periodic scanning
setInterval(runScan, SCAN_INTERVAL);
setInterval(sendHeartbeat, 60000);

// Run initial scan after extension loads
setTimeout(runScan, 5000);

console.log('Jayce Extension v3.0 - WizTheory Rotation Scanner loaded');
