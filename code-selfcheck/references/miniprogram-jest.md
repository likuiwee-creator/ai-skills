# 微信小程序页面在 node 里跑 jest 单测：踩坑与可用模板

目标：不经 `miniprogram-simulate`，只用 jest + 手写 mock，就能在 node 里实例化页面、调 `onLoad`/`toggleFav` 等真实方法，并拿到覆盖率。

## 一、为什么以前说「页面跑不了」
早期只用 c8 量 `utils/**`，页面代码依赖小程序运行时（`wx`、`getApp`、`Page`）所以无法在 node 里 require。加了 mock 后页面即可测，且覆盖率真实（交付时实测 detail 72% 行 / index 50% 行）。

## 二、目录布局
```
miniprogram/
  jest.config.js
  __tests__/
    setup.js        # wx / getApp / Page mock
    detail.test.js
    index.test.js
```
注意产物目录 `coverage/` 要进 `.gitignore`。

## 三、jest.config.js 要点
```js
module.exports = {
  testEnvironment: 'node',
  rootDir: __dirname,
  setupFilesAfterEnv: ['<rootDir>/__tests__/setup.js'],  // 必须是 AfterEnv
  collectCoverageFrom: ['pages/**/*.js', 'utils/**/*.js'],
  coveragePathIgnorePatterns: ['/node_modules/'],
  testMatch: ['**/__tests__/**/*.test.js'],
};
```
- `afterEach` 若放 `setupFiles`，jest 报错（框架未注入）；放 `setupFilesAfterEnv` 才可用。
- `setup.js` 本身要在页面 require 之前生效，`setupFilesAfterEnv` 仍早于测试文件 require，满足要求。

## 四、setup.js 最小 mock（可直接改用）
必须 mock 齐：页面里实际调用到的每个 `wx.*`。典型清单：
`showToast / showModal / navigateTo / redirectTo / switchTab / setClipboardData / setNavigationBarTitle / openLocation / navigateToMiniProgram / getSystemInfoSync(可改 getWindowInfo) / getStorageSync / setStorageSync / removeStorageSync`。

`Page` mock 要能捕获页面对象并支持**路径键 setData**（小程序允许 `"list[0].inFav"` 这种写法，用 `Object.assign` 只设顶层会导致断言全错）：
```js
global.Page = function (o) {
  o.data = o.data || {};
  o.setData = function (d) {
    Object.keys(d).forEach(function (k) {
      // 支持 a.b[0].c
      const parts = k.replace(/\[(\d+)\]/g, '.$1').split('.');
      let cur = this.data;
      for (let i = 0; i < parts.length - 1; i++) {
        if (cur[parts[i]] == null) cur[parts[i]] = /^\d+$/.test(parts[i + 1]) ? [] : {};
        cur = cur[parts[i]];
      }
      cur[parts[parts.length - 1]] = d[k];
    });
  };
  global.__lastPage = o;
};
```

## 五、两个致命坑

### 1. jest 模块注册表不走 `require.cache`
用 `delete require.cache[p]` 清缓存**无效**，第二次 `require` 不会重新执行 `Page()`，`global.__lastPage` 仍为 null。必须：
```js
beforeEach(function () { jest.resetModules(); global.__lastPage = null; });
function loadPage() {
  const p = path.resolve(__dirname, '../pages/detail/detail.js');
  jest.resetModules();
  require(p);
  return global.__lastPage;
}
```

### 2. 共享状态要复位
页面常在模块级取 `const app = getApp()`，跨用例共享同一个 `appData`。若某用例调了「切换城市」，会污染后续所有用例。`beforeEach` 里重置 `appData` 为初始值。

## 六、运行命令
```bash
cd miniprogram && npx jest --coverage
```
必须 `cd` 进去再跑。`jest --config miniprogram/jest.config.js` 会把相对路径当目录解析而找不到配置。

## 七、能测什么（实测有效的断言类型）
- `onLoad({name, city})` 能正确解析参数、找不到时安全降级
- 收藏 `toggleFav`：加/删、写 storage、持久化失败时回滚内存态
- 跨城同名场景不互相误删（复合键 `city::name`）
- `facScore` / `facScoreTxt` 等派生计算
- 空数据/异常入参不抛错

不适合测：真实渲染（WXML）、真实滚动、动画 —— 这些才需要 `miniprogram-simulate`，收益低于维护成本。
