// Renders logo-motion.html to MP4. Usage: node render.js out.mp4 WIDTH HEIGHT [--frames t1,t2]
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const path = require('path');
(async () => {
  const [out, w, h] = process.argv.slice(2);
  const fi = process.argv.indexOf('--frames');
  const stills = fi > 0 ? process.argv[fi + 1].split(',').map(Number) : null;
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: +w, height: +h } });
  await page.goto('file://' + path.resolve(__dirname, 'logo-motion.html') + `?render=1&w=${w}&h=${h}`);
  await page.waitForLoadState('networkidle');
  const { DURATION, FPS } = await page.evaluate(() => ({ DURATION, FPS }));
  if (stills) { for (const t of stills) { await page.evaluate(t => render(t), t); await page.screenshot({ path: `preview_${w}x${h}_${t}.png` }); } await browser.close(); return; }
  const n = Math.round(DURATION * FPS);
  const ff = spawn('ffmpeg', ['-y', '-v', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'png', '-i', '-',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '16', '-preset', 'slow', '-movflags', '+faststart', out], { stdio: ['pipe', 'inherit', 'inherit'] });
  for (let f = 0; f < n; f++) {
    await page.evaluate(t => render(t), f / FPS);
    const buf = await page.screenshot({ type: 'png' });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
  }
  ff.stdin.end(); await new Promise(r => ff.on('close', r)); await browser.close();
  console.log('wrote ' + out);
})();
