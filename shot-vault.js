/**
 * 04 节两张原截图 · 解密成 blob: URL（shot-vault.js）
 *
 * 形态参照 shuangxiugou/why-shuangxiugou.html 的「照片彩蛋」：仓库里只有
 * .enc 密文容器（scripts/encrypt-shots.mjs 生成，PBKDF2-SHA256 21 万次
 * + AES-256-GCM），页面 img 只写 data-enc，不写 src；本脚本取密文、在
 * 浏览器本地解密成 Blob，再用 URL.createObjectURL 生成 blob: 地址写进
 * img.src。页面源码和仓库里都不存在可直接打开的静态图片地址。
 *
 * ⚠️ 诚实的安全口径：解密口令写在本文件里（浏览器要用），所以防得住翻
 *   仓库 / clone 的人，防不住刻意读前端源码的人。这里解决的是「仓库不躺
 *   明文、页面不暴露静态图片 URL」，不是访问控制；本页也没有 Star 门禁，
 *   04 节的图是公开留存的证据，读者应当能直接看到。
 *
 * 页面契约（picks.html）：
 *   - <img data-enc="./assets/xxx.jpg.enc" alt="…">，不放 src；
 *   - #shot-status（.shot-status）为解密状态位，失败时出红字；
 *   - 点击放大仍由页面内联的 lightbox 逻辑负责：解密后 img.src 是 blob:，
 *     灯箱读 img.getAttribute('src') 即可，点击前 src 为空必须拦住。
 *
 * 形态：UMD——浏览器挂在 window.DDFCShotVault 并自动 mount；Node 里
 * module.exports 供本地测试注入桩验证解密链路。
 */
(function (root, factory) {
  var api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { root.DDFCShotVault = api; if (typeof api.mount === 'function') api.mount(); }
})(typeof self !== 'undefined' ? self : this, function (root) {
  'use strict';

  /* 与 scripts/encrypt-shots.mjs 的 PASSPHRASE 必须逐字一致；
     check_site.py 会反查比对，换口令两边一起改再重跑加密脚本。 */
  var PASSPHRASE = 'ddfc-shot-vault-9mQ2vR7kLpX4tNb8';
  var CONTAINER_V = 1;

  function impls(opts) {
    opts = opts || {};
    var g = (typeof globalThis !== 'undefined') ? globalThis : root;
    return {
      fetch: opts.fetch || (root.fetch ? root.fetch.bind(root) : null),
      subtle: opts.subtle || (root.crypto && root.crypto.subtle)
        || (g.crypto && g.crypto.subtle) || null,
      atob: opts.atob || root.atob || g.atob || null,
      Blob: opts.Blob || root.Blob || g.Blob || null,
      TextEncoder: opts.TextEncoder || root.TextEncoder || g.TextEncoder || null,
      createObjectURL: opts.createObjectURL
        || (root.URL && root.URL.createObjectURL && root.URL.createObjectURL.bind(root.URL))
        || (g.URL && g.URL.createObjectURL && g.URL.createObjectURL.bind(g.URL))
        || null,
      revokeObjectURL: opts.revokeObjectURL
        || (root.URL && root.URL.revokeObjectURL && root.URL.revokeObjectURL.bind(root.URL))
        || (g.URL && g.URL.revokeObjectURL && g.URL.revokeObjectURL.bind(g.URL))
        || null,
      passphrase: opts.passphrase || PASSPHRASE
    };
  }

  /** base64 → Uint8Array（& 0xff 防 charCode 超 255 时高位污染） */
  function b64ToBuf(b64, atobImpl) {
    var bin = atobImpl(b64);
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i) & 0xff;
    return bytes;
  }

  function deriveKey(passphrase, salt, iter, impl) {
    var enc = new impl.TextEncoder();
    return impl.subtle.importKey('raw', enc.encode(passphrase), 'PBKDF2', false, ['deriveKey'])
      .then(function (base) {
        return impl.subtle.deriveKey(
          { name: 'PBKDF2', salt: salt, iterations: iter, hash: 'SHA-256' },
          base,
          { name: 'AES-GCM', length: 256 },
          false,
          ['decrypt']
        );
      });
  }

  /** AES-GCM 要求 tag 附在密文尾部；data 与 tag 必须分别 base64 解码再拼 */
  function decryptContainer(container, impl) {
    if (!container || container.v !== CONTAINER_V) {
      return Promise.reject(new Error('容器版本不对（v=' + (container && container.v) + '）'));
    }
    var body = b64ToBuf(container.data, impl.atob);
    var tag = b64ToBuf(container.tag, impl.atob);
    var buf = new Uint8Array(body.length + tag.length);
    buf.set(body, 0);
    buf.set(tag, body.length);
    return deriveKey(impl.passphrase, b64ToBuf(container.salt, impl.atob), container.iter, impl)
      .then(function (key) {
        return impl.subtle.decrypt(
          { name: 'AES-GCM', iv: b64ToBuf(container.iv, impl.atob), tagLength: 128 },
          key,
          buf
        );
      })
      .then(function (plain) {
        return new impl.Blob([plain], { type: container.type || 'image/jpeg' });
      });
  }

  /** 取一个 .enc 并解密成 blob: URL */
  function loadOne(url, impl) {
    return impl.fetch(url).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    }).then(function (container) {
      return decryptContainer(container, impl);
    }).then(function (blob) {
      return impl.createObjectURL(blob);
    });
  }

  /**
   * reveal(doc, opts) → Promise
   * 两张全部解密成功才写 src（半截图比没有更糟）；任一失败：状态位出红字、
   * 已建的 blob: URL 全部撤销，绝不留空框当成功。
   */
  function reveal(doc, opts) {
    opts = opts || {};
    var impl = impls(opts);
    doc = doc || (typeof document !== 'undefined' ? document : null);
    if (!doc) return Promise.reject(new Error('document 缺失'));
    var grid = doc.getElementById('shots-grid');
    if (!grid) return Promise.reject(new Error('截图网格节点缺失'));
    if (grid.getAttribute('data-vault-done') === '1') return Promise.resolve();

    var status = doc.getElementById('shot-status');
    function setStatus(text, kind) {
      if (!status) return;
      status.textContent = text || '';
      status.hidden = !text;
      status.className = 'shot-status' + (kind ? ' shot-status--' + kind : '');
    }
    if (!impl.fetch || !impl.subtle || !impl.atob || !impl.Blob
      || !impl.TextEncoder || !impl.createObjectURL) {
      setStatus('浏览器不支持 Web Crypto，无法解密这两张截图。', 'err');
      return Promise.resolve();
    }

    var imgs = grid.querySelectorAll('img[data-enc]');
    if (imgs.length !== 2) {
      setStatus('截图节点缺失（data-enc），刷新页面试试。', 'err');
      return Promise.resolve();
    }

    setStatus('正在解密截图…', 'check');
    var created = [];
    var jobs = [];
    for (var i = 0; i < imgs.length; i++) {
      jobs.push(loadOne(imgs[i].getAttribute('data-enc'), impl).then(function (url) {
        created.push(url);
        return url;
      }));
    }
    return Promise.all(jobs).then(function (urls) {
      for (var j = 0; j < imgs.length; j++) imgs[j].setAttribute('src', urls[j]);
      grid.hidden = false;
      grid.setAttribute('data-vault-done', '1');
      setStatus('', '');
      if (root.addEventListener && impl.revokeObjectURL) {
        root.addEventListener('pagehide', function () {
          for (var k = 0; k < created.length; k++) {
            try { impl.revokeObjectURL(created[k]); } catch (e) {}
          }
        }, { once: true });
      }
    }).catch(function (err) {
      for (var k = 0; k < created.length; k++) {
        try { if (impl.revokeObjectURL) impl.revokeObjectURL(created[k]); } catch (e) {}
      }
      setStatus('截图解密失败（' + ((err && err.message) || '未知错误')
        + '）。刷新页面试试；反复失败请检查浏览器是否禁用了 JavaScript。', 'err');
    });
  }

  /** mount(opts)：页面加载完自动解密；Node 里不自动跑（由测试显式调 reveal） */
  function mount(opts) {
    opts = opts || {};
    var doc = opts.document || (typeof document !== 'undefined' ? document : null);
    if (!doc) return null;
    function start() { reveal(doc, opts).catch(function () {}); }
    if (doc.readyState === 'loading') {
      doc.addEventListener('DOMContentLoaded', start, { once: true });
    } else {
      start();
    }
    return { reveal: reveal };
  }

  return {
    decryptContainer: decryptContainer,
    reveal: reveal,
    mount: mount,
    b64ToBuf: b64ToBuf
  };
});
