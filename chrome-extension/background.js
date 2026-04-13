const VPS_URL = "http://104.236.105.118:5000/tokens";
const API_KEY = "jayce_collector_2026_secret_key";

// Auto-capture interval (10 minutes = 600000ms)
const AUTO_CAPTURE_INTERVAL = 10 * 60 * 1000;

const URLS = {
  TRENDING: "https://dexscreener.com/?rankBy=trendingScoreH6&order=desc&chainIds=solana&dexIds=pumpswap,pumpfun&minLiq=10000&minMarketCap=100000&minAge=1&launchpads=1",
  VOL_5M: "https://dexscreener.com/?rankBy=priceChangeM5&order=desc&chainIds=solana&dexIds=pumpswap,pumpfun&minLiq=10000&minMarketCap=100000&minAge=1&launchpads=1",
  VOL_1H: "https://dexscreener.com/?rankBy=priceChangeH1&order=desc&chainIds=solana&dexIds=pumpswap,pumpfun&minLiq=10000&minMarketCap=100000&minAge=1&launchpads=1"
};

// Send tokens to VPS
async function sendToVPS(tokens, source) {
  try {
    const response = await fetch(VPS_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
      },
      body: JSON.stringify({ tokens, source })
    });
    const data = await response.json();
    console.log(`[Jayce] Sent ${tokens.length} ${source} tokens`);
    return data;
  } catch (err) {
    console.error("[Jayce] Send error:", err);
    return null;
  }
}

// Scrape function to inject into page
function scrapeTokens(source) {
  const tokens = [];
  const seen = new Set();
  let rank = 0;
  
  const rows = document.querySelectorAll('a[href*="/solana/"]');
  
  rows.forEach(row => {
    try {
      const href = row.getAttribute('href') || '';
      const match = href.match(/\/solana\/([a-zA-Z0-9]+)/);
      if (!match) return;
      
      const pairAddress = match[1];
      if (seen.has(pairAddress)) return;
      if (pairAddress.length < 30) return;
      seen.add(pairAddress);
      rank++;
      
      let symbol = '???';
      
      const symbolEl = row.querySelector('[class*="symbol" i], [class*="Symbol" i]');
      if (symbolEl && symbolEl.textContent.trim()) {
        symbol = symbolEl.textContent.trim().split(/[\s\/\n]/)[0];
      }
      
      if (symbol === '???') {
        const walker = document.createTreeWalker(row, NodeFilter.SHOW_TEXT, null, false);
        while (walker.nextNode()) {
          const text = walker.currentNode.textContent.trim();
          if (text.length >= 2 && text.length <= 20 && 
              !text.includes('$') && !text.includes('%') && 
              !text.includes('.') && !text.match(/^[\d,]+$/)) {
            symbol = text.split(/[\s\/\n]/)[0];
            break;
          }
        }
      }
      
      symbol = symbol.replace(/[^a-zA-Z0-9]/g, '').substring(0, 20) || '???';
      
      tokens.push({
        symbol: symbol,
        pair_address: pairAddress,
        contract_address: '',
        source: source,
        rank: rank,
        url: 'https://dexscreener.com' + href
      });
    } catch (e) {}
  });
  
  return tokens;
}

// Capture a single rotation
async function captureRotation(source) {
  console.log(`[Jayce Auto] Capturing ${source}...`);
  
  const url = URLS[source];
  
  // Create or reuse a tab for scraping
  const tabs = await chrome.tabs.query({url: "https://dexscreener.com/*"});
  let tab;
  
  if (tabs.length > 0) {
    tab = tabs[0];
    await chrome.tabs.update(tab.id, {url: url});
  } else {
    tab = await chrome.tabs.create({url: url, active: false});
  }
  
  // Wait for page to load
  await new Promise(r => setTimeout(r, 6000));
  
  // Scrape tokens
  const results = await chrome.scripting.executeScript({
    target: {tabId: tab.id},
    func: scrapeTokens,
    args: [source]
  });
  
  const tokens = results[0]?.result || [];
  
  if (tokens.length > 0) {
    await sendToVPS(tokens.slice(0, 100), source);
  }
  
  return tokens.length;
}

// Capture all 3 rotations
async function captureAll() {
  console.log('[Jayce Auto] Starting auto-capture cycle...');
  
  try {
    await captureRotation('TRENDING');
    await new Promise(r => setTimeout(r, 2000));
    
    await captureRotation('VOL_5M');
    await new Promise(r => setTimeout(r, 2000));
    
    await captureRotation('VOL_1H');
    
    console.log('[Jayce Auto] Cycle complete!');
    
    // Send heartbeat
    await fetch("http://104.236.105.118:5000/heartbeat", {
      method: "POST",
      headers: { "X-API-Key": API_KEY }
    });
  } catch (e) {
    console.error('[Jayce Auto] Error:', e);
  }
}

// Listen for messages from popup
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "SEND_TOKENS") {
    sendToVPS(msg.tokens, msg.source).then(data => {
      sendResponse({success: true, data});
    }).catch(e => {
      sendResponse({success: false, error: e.message});
    });
    return true;
  }
  
  if (msg.type === "MANUAL_CAPTURE_ALL") {
    captureAll().then(() => sendResponse({success: true}));
    return true;
  }
});

// Start auto-capture loop
console.log('[Jayce] Auto-capture enabled - every 10 minutes');

// Initial capture after 30 seconds
setTimeout(captureAll, 30000);

// Then every 10 minutes
setInterval(captureAll, AUTO_CAPTURE_INTERVAL);

// Heartbeat every 60 seconds
setInterval(async () => {
  try {
    await fetch("http://104.236.105.118:5000/heartbeat", {
      method: "POST",
      headers: { "X-API-Key": API_KEY }
    });
  } catch (e) {}
}, 60000);
