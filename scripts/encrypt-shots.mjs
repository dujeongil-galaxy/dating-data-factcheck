/* ==========================================================================
   04 节两张原截图 → .enc 密文容器
   --------------------------------------------------------------------------
   站长 2026-11-07 的原话是「链接改为 blob 格式」（当时被误听成 blog）。
   目标形态参照 shuangxiugou/why-shuangxiugou.html 的「照片彩蛋」：
   仓库里只有 .enc 密文，浏览器本地解密后用 URL.createObjectURL 生成
   blob:https://… 地址写进 img.src，页面上不存在任何可直接打开的素材 URL。

   用法（明文原图只留在本机备份，不进仓库）：
     node scripts/encrypt-shots.mjs --src-dir="C:/Users/dujeo/WorkBuddy/factcheck-素材备份"
     node scripts/encrypt-shots.mjs --src-dir=<目录> --key=<新口令>

   ⚠️ 换口令必须同步改 shot-vault.js 的 PASSPHRASE，再重跑本脚本；
      check_site.py 会比对两处口令，不一致直接判红。

   ⚠️ 诚实的安全口径：解密口令写在前端源码里，所以「防得住翻仓库／clone
      的人，防不住刻意读前端源码的人」。这套方案解决的是「仓库不躺明文、
      页面不暴露静态图片地址」，不是访问控制。

   参数与 shuangxiugou 的 photo-vault / notes 同一套：
   PBKDF2-SHA256（21 万次）+ AES-256-GCM，salt/iv 每次随机。
   容器是单行 JSON：{ v, alg, iter, name, type, salt, iv, tag, data }。
   ========================================================================== */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

const ITERATIONS = 210_000;
const KEYLEN = 32;
const SALT_BYTES = 16;
const IV_BYTES = 12;

/* 与 shot-vault.js 的 PASSPHRASE 必须逐字一致（check_site.py 会反查） */
const PASSPHRASE = 'ddfc-shot-vault-9mQ2vR7kLpX4tNb8';

const SHOTS = [
  { src: 'soul-2019-comments-1.jpg', out: 'assets/soul-2019-comments-1.jpg.enc', type: 'image/jpeg' },
  { src: 'soul-2019-comments-2.jpg', out: 'assets/soul-2019-comments-2.jpg.enc', type: 'image/jpeg' },
];

function deriveKey(passphrase, salt) {
  return crypto.pbkdf2Sync(passphrase, salt, ITERATIONS, KEYLEN, 'sha256');
}

function encryptBuffer(plaintext, name, type, passphrase) {
  const salt = crypto.randomBytes(SALT_BYTES);
  const iv = crypto.randomBytes(IV_BYTES);
  const key = deriveKey(passphrase, salt);
  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
  const data = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  const tag = cipher.getAuthTag();
  return {
    v: 1,
    alg: 'PBKDF2-SHA256+AES-256-GCM',
    iter: ITERATIONS,
    name,
    type,
    salt: salt.toString('base64'),
    iv: iv.toString('base64'),
    tag: tag.toString('base64'),
    data: data.toString('base64'),
  };
}

/** 当场解回来比对字节，参数写错不会带着坏密文上线 */
function decryptContainer(container, passphrase) {
  const key = deriveKey(passphrase, Buffer.from(container.salt, 'base64'));
  const decipher = crypto.createDecipheriv('aes-256-gcm', key, Buffer.from(container.iv, 'base64'));
  decipher.setAuthTag(Buffer.from(container.tag, 'base64'));
  return Buffer.concat([
    decipher.update(Buffer.from(container.data, 'base64')),
    decipher.final(),
  ]);
}

function main() {
  const srcArg = process.argv.find((a) => a.startsWith('--src-dir='));
  const keyArg = process.argv.find((a) => a.startsWith('--key='));
  if (!srcArg) {
    console.error('✗ 缺 --src-dir=<仓库外明文备份目录>；明文原图不得放进本仓库。');
    process.exit(1);
  }
  const srcDir = path.resolve(srcArg.slice('--src-dir='.length).replace(/^["']|["']$/g, ''));
  const passphrase = keyArg ? keyArg.slice('--key='.length) : PASSPHRASE;
  if (passphrase.length < 12) {
    console.error('✗ 口令太短（≥12 位）。');
    process.exit(1);
  }

  let failed = 0;
  for (const shot of SHOTS) {
    const srcPath = path.join(srcDir, shot.src);
    const outPath = path.join(ROOT, shot.out);
    if (!fs.existsSync(srcPath)) {
      console.error(`✗ 明文不存在：${srcPath}`);
      failed++;
      continue;
    }
    const plaintext = fs.readFileSync(srcPath);
    const container = encryptBuffer(plaintext, shot.src, shot.type, passphrase);
    const roundtrip = decryptContainer(container, passphrase);
    if (!roundtrip.equals(plaintext)) {
      console.error(`✗ ${shot.src} 加密自检失败：解密结果与原文不一致，已中止。`);
      failed++;
      continue;
    }
    fs.writeFileSync(outPath, JSON.stringify(container));
    console.log(`✓ ${shot.src} → ${shot.out}`);
    console.log(`  明文 ${plaintext.length} B → 密文容器 ${fs.statSync(outPath).size} B，往返自检通过`);
  }
  if (failed) {
    console.error(`\n${failed} 个素材加密失败。`);
    process.exit(1);
  }
  console.log('\n完成。仓库里只应有 .enc 密文；明文原图留在仓库外备份目录，勿提交。');
}

main();
