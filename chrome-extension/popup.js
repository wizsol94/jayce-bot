const URLS = {
  TRENDING: "https://dexscreener.com/?rankBy=trendingScoreH6&order=desc&chainIds=solana&dexIds=pumpswap,pumpfun&minLiq=10000&minMarketCap=100000&minAge=1&launchpads=1",
  VOL_5M: "https://dexscreener.com/?rankBy=priceChangeM5&order=desc&chainIds=solana&dexIds=pumpswap,pumpfun&minLiq=10000&minMarketCap=100000&minAge=1&launchpads=1",
  VOL_1H: "https://dexscreener.com/?rankBy=priceChangeH1&order=desc&chainIds=solana&dexIds=pumpswap,pumpfun&minLiq=10000&minMarketCap=100000&minAge=1&launchpads=1"
};

const status = document.getElementById('status');

function updateStatus(msg) {
  status.textContent = msg;
}

function scrapeTokens(source) {
  const tokens = [];
  const seen = new Set();
  let rank = 0;
  
  // Find all token row links
  const rows = document.querySelectorAll('a[href*="/solana/"]');
  
  rows.forEach(row => {
    try {
      const href = row.getAttribute('href') || '';
      const match = href.match(/\/solana\/([a-zA-Z0-9]+)/);
      if (!match) return;
      
      const pairAddress = match[1];
      if (seen.has(pairAddress)) return;
      if (pairAddress.length < 30) return; // Skip short invalid addresses
      seen.add(pairAddress);
      rank++;
      
      // Try multiple methods to find symbol
      let symbol = '???';
      
      // Method 1: Look for ds-dex-table-row-col-token-symbol class or similar
      const symbolEl = row.querySelector('[class*="symbol" i], [class*="Symbol" i], [class*="token-name" i]');
      if (symbolEl && symbolEl.textContent.trim()) {
        symbol = symbolEl.textContent.trim().split(/[\s\/\n]/)[0];
      }
      
      // Method 2: Get first short text from the row
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
      
      // Method 3: Check row's direct child spans
      if (symbol === '???') {
        const spans = row.querySelectorAll('span, div');
        for (const span of spans) {
          const text = span.textContent?.trim();
          if (text && text.length >= 2 && text.length <= 15 && 
              !text.includes('$') && !text.includes('%') &&
              !text.match(/^[\d.,]+$/) && !text.includes('solana')) {
            symbol = text.split(/[\s\/\n]/)[0];
            break;
          }
        }
      }
      
      // Clean up symbol
      symbol = symbol.replace(/[^a-zA-Z0-9]/g, '').substring(0, 20) || '???';
      
      tokens.push({
        symbol: symbol,
        pair_address: pairAddress,
        contract_address: '',
        source: source,
        rank: rank,
        url: 'https://dexscreener.com' + href
      });
    } catch (e) {
      console.error('[Jayce] Scrape error:', e);
    }
  });
  
  console.log('[Jayce] Scraped tokens:', tokens.slice(0, 5));
  return tokens;
}

async function captureRotation(source) {
  updateStatus('Opening ' + source + '...');
  
  const url = URLS[source];
  
  const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
  await chrome.tabs.update(tab.id, {url: url});
  
  updateStatus('Loading... (6 sec)');
  
  // Wait longer for page to fully render
  await new Promise(r => setTimeout(r, 6000));
  
  updateStatus('Scraping ' + source + '...');
  
  const results = await chrome.scripting.executeScript({
    target: {tabId: tab.id},
    func: scrapeTokens,
    args: [source]
  });
  
  const tokens = results[0]?.result || [];
  
  if (tokens.length === 0) {
    updateStatus('⚠️ No tokens found');
    return 0;
  }
  
  updateStatus('Sending ' + tokens.length + ' tokens...');
  
  const response = await chrome.runtime.sendMessage({
    type: 'SEND_TOKENS',
    tokens: tokens.slice(0, 100),
    source: source
  });
  
  if (response?.success) {
    updateStatus('✅ ' + source + ': ' + tokens.length + ' sent!');
  } else {
    updateStatus('❌ Send failed: ' + (response?.error || 'unknown'));
  }
  
  return tokens.length;
}

async function captureAll() {
  updateStatus('Capturing all 3 rotations...');
  
  let total = 0;
  
  total += await captureRotation('TRENDING');
  await new Promise(r => setTimeout(r, 1500));
  
  total += await captureRotation('VOL_5M');
  await new Promise(r => setTimeout(r, 1500));
  
  total += await captureRotation('VOL_1H');
  
  updateStatus('✅ All done! ' + total + ' total tokens');
}

document.getElementById('btnTop').onclick = () => captureRotation('TRENDING');
document.getElementById('btn5m').onclick = () => captureRotation('VOL_5M');
document.getElementById('btn1h').onclick = () => captureRotation('VOL_1H');
document.getElementById('btnAll').onclick = captureAll;
