// Renders bowl-motion.html frame-by-frame into an MP4 (1080x1920, 30fps).
// Usage: node render.js [out.mp4] [--frames t1,t2,...]
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const path = require('path');
(async () => {
  const args = process.argv.slice(2);
  const fi = args.indexOf('--frames');
  const stills = fi >= 0 ? args[fi + 1].split(',').map(Number) : null;
  const out = args.find(a => a.endsWith('.mp4')) || 'green-vs-colorful.mp4';
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
  await page.goto('file://' + path.resolve(__dirname, 'bowl-motion.html') + '?render=1');
  await page.waitForLoadState('networkidle');
  await page.evaluate(() => document.fonts.ready);
  if (stills) {
    for (const t of stills) { await page.evaluate(t => render(t), t); await page.screenshot({ path: `preview_${t}.png` }); }
    await browser.close(); return;
  }
  const { DURATION, FPS } = await page.evaluate(() => ({ DURATION, FPS }));
  const n = Math.round(DURATION * FPS);
  const ff = spawn('ffmpeg', ['-y', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-preset', 'medium', '-movflags', '+faststart', out], { stdio: ['pipe', 'inherit', 'inherit'] });
  for (let f = 0; f < n; f++) {
    await page.evaluate(t => render(t), f / FPS);
    const buf = await page.screenshot({ type: 'jpeg', quality: 95 });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (f % 150 === 0) console.error(`frame ${f}/${n}`);
  }
  ff.stdin.end(); await new Promise(r => ff.on('close', r)); await browser.close();
  console.error('wrote ' + out);
})();
