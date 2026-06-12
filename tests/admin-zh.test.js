const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const scriptPath = path.join(__dirname, '..', 'overrides', 'emailengine', 'static', 'js', 'admin-zh.js');
const source = fs.readFileSync(scriptPath, 'utf8');

const context = {
    console,
    window: {},
    document: {
        title: 'EmailEngine - Dashboard',
        readyState: 'loading',
        addEventListener() {},
        createTreeWalker() {
            return { nextNode: () => false };
        },
        querySelectorAll() {
            return [];
        }
    },
    NodeFilter: { SHOW_TEXT: 4 },
    MutationObserver: class {
        observe() {}
    }
};

vm.createContext(context);
vm.runInContext(source, context);

assert.strictEqual(context.window.EmailEngineAdminZh.translateText('Dashboard'), '仪表盘');
assert.strictEqual(context.window.EmailEngineAdminZh.translateText('Email Accounts'), '邮箱账户');
assert.strictEqual(context.window.EmailEngineAdminZh.translateText('License key missing'), '缺少许可证密钥');
assert.strictEqual(context.window.EmailEngineAdminZh.translateText('Search'), '搜索');

console.log('admin-zh translations ok');
