let isCollecting = false;

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'collectTokens' && !isCollecting) {
    collectAllTokens();
  }
  sendResponse({ status: 'ok' });
  return true;
});

async function collectAllTokens() {
  isCollecting = true;
  console.log('Jayce: Starting WizTheory rotation scan...');
  
  const allTokens = [];
  const sourceCounts = { TRENDING: 0, VOL_5M: 0, VOL_1H: 0 };
  
  try {
    // ══════════════════════════════════════════════════════════════
    // STEP 1: MAIN DEXSCREENER LIST (1-150)
    // Your exact filtered universe
    // ══════════════════════════════════════════════════════════════
    console.log('Jayce: STEP 1 - Main Dexscreener List (Trending H6)...');
    
    // Navigate to your exact filtered URL
    const mainUrl = 'https://dexscreener.com/?rankBy=trendingScoreH6&order=desc&chainIds=solana&dexIds=pumpswap,pumpfun,raydium&minLiq=10000&minMarketCap=100000&minAge=1&profile=0&launchpads=1';
    
    if (!window.location.href.includes('trendingScoreH6')) {
      window.location.href = mainUrl;
      await sleep(4000);
    }
    
    await waitForTokens();
    await scrollToLoadAll(150);
    
    const trendingTokens = extractTokens('TRENDING');
    allTokens.push(...trendingTokens);
    sourceCounts.TRENDING = trendingTokens.length;
    console.log('Main List: ' + trendingTokens.length + ' tokens');
    
    // ══════════════════════════════════════════════════════════════
    // STEP 2: 5-MINUTE VOLUME MOVERS (Top 30-50)
    // ══════════════════════════════════════════════════════════════
    console.log('Jayce: STEP 2 - 5m Volume Movers...');
    
    const vol5mUrl = 'https://dexscreener.com/?rankBy=volume5m&order=desc&chainIds=solana&dexIds=pumpswap,pumpfun,raydium&minLiq=10000&minMarketCap=100000&minAge=1&profile=0&launchpads=1';
    window.location.href = vol5mUrl;
    await sleep(4000);
    await waitForTokens();
    await scrollToLoadAll(50);
    
    const vol5mTokens = extractTokens('VOL_5M');
    allTokens.push(...vol5mTokens);
    sourceCounts.VOL_5M = vol5mTokens.length;
    console.log('5m Volume: ' + vol5mTokens.length + ' tokens');
    
    // ══════════════════════════════════════════════════════════════
    // STEP 3: 1-HOUR VOLUME MOVERS (Top 30-50)
    // ══════════════════════════════════════════════════════════════
    console.log('Jayce: STEP 3 - 1h Volume Movers...');
    
    const vol1hUrl = 'https://dexscreener.com/?rankBy=volume1h&order=desc&chainIds=solana&dexIds=pumpswap,pumpfun,raydium&minLiq=10000&minMarketCap=100000&minAge=1&profile=0&launchpads=1';
    window.location.href = vol1hUrl;
    await sleep(4000);
    await waitForTokens();
    await scrollToLoadAll(50);
    
    const vol1hTokens = extractTokens('VOL_1H');
    allTokens.push(...vol1hTokens);
    sourceCounts.VOL_1H = vol1hTokens.length;
    console.log('1h Volume: ' + vol1hTokens.length + ' tokens');
    
    // ══════════════════════════════════════════════════════════════
    // STEP 4: RETURN TO MAIN LIST (for next cycle)
    // ══════════════════════════════════════════════════════════════
    console.log('Jayce: Returning to Main List for next cycle...');
    window.location.href = mainUrl;
    await sleep(2000);
    
    // ══════════════════════════════════════════════════════════════
    // DEDUPE AND SEND
    // ══════════════════════════════════════════════════════════════
    const unique = dedupeTokens(allTokens);
    console.log('Jayce: Total unique tokens: ' + unique.length);
    console.log('  TRENDING: ' + sourceCounts.TRENDING);
    console.log('  5M VOL: ' + sourceCounts.VOL_5M);
    console.log('  1H VOL: ' + sourceCounts.VOL_1H);
    
    // Send to background for processing
    chrome.runtime.sendMessage({
      action: 'tokensCollected',
      data: { tokens: unique, source_counts: sourceCounts }
    });
    
  } catch (e) {
    console.error('Jayce: Collection error:', e);
  }
  
  isCollecting = false;
}

async function waitForTokens() {
  for (let i = 0; i < 30; i++) {
    if (document.querySelectorAll('a[href*="/solana/"]').length > 5) return;
    await sleep(500);
  }
}

async function scrollToLoadAll(targetCount = 150) {
  for (let i = 0; i < 30; i++) {
    window.scrollBy(0, 1000);
    await sleep(400);
    const current = document.querySelectorAll('a[href*="/solana/"]').length;
    if (current >= targetCount) break;
  }
  window.scrollTo(0, 0);
  await sleep(500);
}

function extractTokens(source) {
  const tokens = [];
  const seen = new Set();
  let rank = 1;
  
  document.querySelectorAll('a[href*="/solana/"]').forEach(row => {
    try {
      const href = row.getAttribute('href') || '';
      const pair = href.split('/solana/')[1]?.split('?')[0]?.split('#')[0];
      if (!pair || pair.length < 30 || seen.has(pair)) return;
      seen.add(pair);
      
      let symbol = '???';
      const rowText = row.innerText || '';
      const lines = rowText.split('\n').map(l => l.trim()).filter(l => l.length > 0);
      
      for (const line of lines) {
        if (/^[\d\$\.\%\-\+\,]+$/.test(line)) continue;
        if (/^\#?\d+$/.test(line)) continue;
        if (line.length > 15 || line.length < 2) continue;
        symbol = line;
        break;
      }
      
      tokens.push({
        symbol: symbol,
        pair_address: pair,
        contract_address: '',
        source: source,
        rank: rank++,
        url: 'https://dexscreener.com/solana/' + pair
      });
      
    } catch (e) {}
  });
  
  return tokens;
}

function dedupeTokens(tokens) {
  const seen = new Set();
  const unique = [];
  
  for (const t of tokens) {
    const key = t.pair_address;
    if (!seen.has(key)) {
      seen.add(key);
      unique.push(t);
    }
  }
  
  return unique;
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
