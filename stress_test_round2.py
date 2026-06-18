#!/usr/bin/env python3
"""
maestro-guard Stress Test Round 2 — FUZZER + deep edge-case testing.

This is a SECOND-PASS stress test that goes more extreme than the first.
Includes a proper fuzzer (200+ random inputs), minified code, TS/JSX,
async complexity, module scripts, property access edge cases, real-world
AI bug patterns, filesystem edge cases, encoding attacks, and spec edge cases.
"""

import os
import sys
import subprocess
import tempfile
import time
import json
import random
import string
import shutil
import traceback
import hashlib

BASE_DIR = "/root/maestro-guard"
sys.path.insert(0, BASE_DIR)

CLI_CMD = [sys.executable, "-m", "maestro_guard.cli", "check"]
RESULTS = {
    "critical": [],
    "moderate": [],
    "minor": [],
    "info": [],
}


def record_issue(severity, category, test_name, issue, detail=""):
    entry = {
        "test": test_name,
        "category": category,
        "issue": issue,
        "detail": detail,
    }
    RESULTS[severity].append(entry)
    icon = {"critical": "🔴", "moderate": "🟡", "minor": "🔵", "info": "ℹ️"}[severity]
    print(f"  {icon} [{severity.upper()}] {test_name}: {issue}")
    if detail:
        for line in detail.split('\n'):
            print(f"     {line}")


def run_cli(filepath, extra_args=None):
    cmd = CLI_CMD + [filepath]
    if extra_args:
        cmd += extra_args

    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=BASE_DIR,
        )
        elapsed = time.time() - start

        json_result = None
        stdout = proc.stdout
        stderr = proc.stderr

        for line in stdout.split('\n'):
            line = line.strip()
            if line.startswith('{'):
                try:
                    json_result = json.loads(line)
                    break
                except json.JSONDecodeError:
                    pass

        passed = None
        if json_result:
            passed = json_result.get("all_passed", False)
        else:
            passed = "ALL CHECKS PASSED" in stdout

        return {
            "exit_code": proc.returncode,
            "passed": passed,
            "stdout": stdout,
            "stderr": stderr,
            "json": json_result,
            "elapsed": elapsed,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": -1,
            "passed": None,
            "stdout": "",
            "stderr": "TIMEOUT",
            "json": None,
            "elapsed": 30,
            "timed_out": True,
        }
    except Exception as e:
        return {
            "exit_code": -2,
            "passed": None,
            "stdout": "",
            "stderr": f"EXCEPTION: {e}\n{traceback.format_exc()}",
            "json": None,
            "elapsed": 0,
            "timed_out": False,
            "exception": str(e),
        }


def run_and_check(test_name, html_content, expected_fail=None, extra_args=None):
    """Write HTML to temp file, run CLI, check for crashes, and record issues."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write(html_content)
        path = f.name

    result = run_cli(path, extra_args)
    _analyze(test_name, result, expected_fail)
    os.unlink(path)
    return result


def _analyze(test_name, result, expected_fail=None):
    if result.get("timed_out"):
        record_issue("critical", "hang", test_name,
                     "Command timed out (30s) — hangs on input",
                     f"stdout: {result['stdout'][:200]}")
        return

    if result.get("exception"):
        record_issue("critical", "crash", test_name,
                     f"Unhandled exception: {result['exception']}",
                     result['stderr'][:500])
        return

    exit_code = result["exit_code"]
    passed = result["passed"]

    if exit_code == -2:
        record_issue("critical", "crash", test_name,
                     "Process crashed with exception",
                     result['stderr'][:500])
        return

    stderr = result.get("stderr", "")
    stdout = result.get("stdout", "")
    if "Traceback (most recent call last)" in stderr or "Traceback (most recent call last)" in stdout:
        tb = (stderr + stdout)[:500]
        record_issue("critical", "crash", test_name,
                     "Unhandled traceback in output", tb)
        return

    if expected_fail is not None:
        if expected_fail and passed:
            record_issue("moderate", "logic", test_name,
                         "Should have FAILED but got PASS (false negative)",
                         f"Expected FAIL, got PASS. exit_code={exit_code}")
        elif not expected_fail and not passed:
            record_issue("moderate", "logic", test_name,
                         "Should have PASSED but got FAIL (false positive)",
                         f"Expected PASS, got FAIL. exit_code={exit_code}")

    if passed is not None:
        if passed and exit_code not in (0, 1):
            record_issue("minor", "consistency", test_name,
                         f"Exit code {exit_code} but result shows PASS")
        elif not passed and exit_code not in (0, 1):
            record_issue("minor", "consistency", test_name,
                         f"Exit code {exit_code} but result shows FAIL")


# ============================================================
# SECTION 1: FUZZER (200+ random inputs)
# ============================================================

def _random_html_structure():
    """Generate a random valid-ish HTML structure."""
    parts = []

    if random.random() < 0.7:
        parts.append('<!DOCTYPE html>\n')

    parts.append('<html>\n<head>\n')
    if random.random() < 0.5:
        parts.append('<meta charset="UTF-8">\n')
    if random.random() < 0.3:
        parts.append(f'<title>{_random_word()}</title>\n')
    parts.append('</head>\n<body>\n')

    # Add some random HTML elements
    num_divs = random.randint(0, 5)
    used_ids = set()
    for _ in range(num_divs):
        depth = random.randint(1, 3)
        for d in range(depth):
            attrs = ""
            if random.random() < 0.4:
                new_id = _random_word()
                used_ids.add(new_id)
                attrs += f' id="{new_id}"'
            if random.random() < 0.3:
                attrs += f' class="{_random_word()}"'
            parts.append(f'<div{attrs}>')

        if random.random() < 0.5:
            parts.append(f'<span>{_random_word()}</span>')
        if random.random() < 0.3:
            parts.append(f'<p>{_random_word()}</p>')

        for d in range(depth):
            parts.append('</div>')

    # Add some inputs/buttons
    if random.random() < 0.4:
        new_id = _random_word()
        used_ids.add(new_id)
        parts.append(f'<button id="{new_id}">{_random_word()}</button>\n')
    if random.random() < 0.3:
        new_id = _random_word()
        used_ids.add(new_id)
        parts.append(f'<input id="{new_id}" type="text">\n')

    return parts, used_ids


def _random_word():
    """Generate a random word."""
    length = random.randint(3, 12)
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(length))


def _random_js_block(used_ids):
    """Generate a random JavaScript block."""
    js = []
    num_statements = random.randint(0, 8)

    for _ in range(num_statements):
        choice = random.random()
        if choice < 0.15:
            # Variable declaration
            var_type = random.choice(['var', 'let', 'const'])
            name = _random_word()
            if random.random() < 0.5:
                val = random.randint(0, 100)
            elif random.random() < 0.3:
                val = f"'{_random_word()}'"
            else:
                val = random.choice(['true', 'false', 'null', 'undefined', f'"hello {_random_word()}"'])
            js.append(f'{var_type} {name} = {val};')
        elif choice < 0.25:
            # Function declaration
            fname = _random_word()
            params = ', '.join(_random_word() for _ in range(random.randint(0, 3)))
            body_lines = []
            for _ in range(random.randint(1, 4)):
                body_lines.append(f'    var {_random_word()} = {random.randint(0, 100)};')
            body_lines.append(f'    return {random.choice([str(random.randint(0, 100)), _random_word()])};')
            js.append(f'function {fname}({params}) {{\n' + '\n'.join(body_lines) + '\n}')
        elif choice < 0.33:
            # Arrow function
            params = random.choice(['', f'{_random_word()}', f'({_random_word()}, {_random_word()})'])
            if random.random() < 0.5:
                body = f'{{ return {random.randint(0, 100)}; }}'
            else:
                body = str(random.randint(0, 100))
            js.append(f'const {_random_word()} = {params} => {body};')
        elif choice < 0.40:
            # Template literal
            words = ' '.join(_random_word() for _ in range(random.randint(2, 5)))
            if random.random() < 0.3:
                words = f'${{{_random_word()}}} ' + words
            js.append(f'const {_random_word()} = `{words}`;')
        elif choice < 0.46:
            # Array literal
            items = ', '.join(str(random.randint(0, 100)) for _ in range(random.randint(1, 6)))
            js.append(f'const {_random_word()} = [{items}];')
        elif choice < 0.52:
            # Object literal
            props = ', '.join(f'{_random_word()}: {random.randint(0, 100)}' for _ in range(random.randint(1, 4)))
            js.append(f'const {_random_word()} = {{{props}}};')
        elif choice < 0.60:
            # getElementById call
            if used_ids:
                target_id = random.choice(list(used_ids) + [_random_word() for _ in range(2)])
                js.append(f'document.getElementById(\'{target_id}\');')
            else:
                js.append(f'document.getElementById(\'{_random_word()}\');')
        elif choice < 0.66:
            # Empty function (handler stub)
            fname = _random_word()
            js.append(f'function {fname}() {{\n}}')
        elif choice < 0.72:
            # console.log
            js.append(f'console.log(\'{_random_word()}\');')
        elif choice < 0.78:
            # console.error
            js.append(f'console.error(\'{_random_word()}\');')
        elif choice < 0.83:
            # addEventListener
            js.append(f'document.getElementById(\'{_random_word()}\').addEventListener(\'click\', {_random_word()});')
        elif choice < 0.88:
            # try/catch
            js.append(f'try {{\n    {_random_word()}();\n}} catch (e) {{\n    console.log(e);\n}}')
        else:
            # Just an expression
            js.append(f'{_random_word()}.{_random_word()}();')

    return '\n'.join(js)


def test_1_fuzzer():
    """FUZZER: 200+ random inputs checking for crashes only."""
    print("\n# [1] FUZZER — 200+ random inputs")
    crash_count = 0
    total = 0

    for i in range(220):
        parts, used_ids = _random_html_structure()
        # Add 0-3 script blocks
        num_scripts = random.randint(0, 3)
        for _ in range(num_scripts):
            js = _random_js_block(used_ids)
            script_type = ""
            if random.random() < 0.1:
                script_type = ' type="application/json"'
                js = json.dumps({"key": _random_word(), "value": random.randint(0, 100)})
            elif random.random() < 0.05:
                script_type = ' type="module"'
            parts.append(f'<script{script_type}>\n{js}\n</script>\n')

        # Maybe add an empty script
        if random.random() < 0.1:
            parts.append('<script></script>')

        parts.append('</body>\n</html>')
        html = ''.join(parts)
        test_name = f"1.{i}: Random fuzz #{i}"

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(html)
            path = f.name

        result = run_cli(path)
        total += 1

        if result.get("timed_out"):
            crash_count += 1
            record_issue("critical", "fuzzer", test_name,
                         "Timeout on random input", f"Input length: {len(html)}")
        elif result.get("exception"):
            crash_count += 1
            record_issue("critical", "fuzzer", test_name,
                         f"Crash: {result['exception']}",
                         f"Input length: {len(html)}, stderr: {result['stderr'][:200]}")
        elif "Traceback" in result.get("stderr", "") or "Traceback" in result.get("stdout", ""):
            crash_count += 1
            record_issue("critical", "fuzzer", test_name,
                         "Unhandled traceback", result['stderr'][:300])
        else:
            # Must exit with 0 or 1, nothing else
            ec = result["exit_code"]
            if ec not in (0, 1):
                crash_count += 1
                record_issue("critical", "fuzzer", test_name,
                             f"Unexpected exit code {ec} (expected 0 or 1)",
                             f"Input length: {len(html)}, stdout: {result['stdout'][:200]}")

        os.unlink(path)

    print(f"  FUZZER RESULTS: {crash_count} crashes out of {total} random inputs")
    if crash_count == 0:
        print(f"  ✅ All {total} random inputs processed cleanly (exit 0 or 1)")


# ============================================================
# SECTION 2: Minified Code (real-world AI output)
# ============================================================

def test_2_minified_code():
    """Minified JS / AI-generated single-page app HTML."""
    print("\n# [2] Minified Code (real-world AI output)")

    # 2a: 50KB of minified JS on a single line (valid ES5)
    print("  [2a] 50KB minified JS...")
    long_var = "a" * 10000
    js_minified = "var " + ",".join(f"a{i}={long_var}" for i in range(5)) + ";"
    js_minified += "function f(){return 42;}var b=function(x){return x+1;};"
    # Pad to ~50KB
    while len(js_minified) < 50000:
        js_minified += "var " + _random_word() + "=" + str(random.randint(0, 9999)) + ";"

    html_2a = f"<html><body><script>{js_minified}</script></body></html>"
    run_and_check("2a: 50KB minified JS (single line)", html_2a)

    # 2b: Minified React-like output (JSX transpiled)
    print("  [2b] Minified React-like output...")
    react_like = """const e=React.createElement;function App(){return e('div',{className:'app'},
e('header',{className:'header'},e('h1',null,'Hello'),e('nav',null,
e('a',{href:'/'},'Home'),e('a',{href:'/about'},'About'))),
e('main',{className:'main'},e('section',{id:'content'},
e('p',null,'Welcome to our app!'),e('button',{id:'cta',onClick:handleClick},'Click Me'))),
e('footer',{className:'footer'},e('p',null,'Copyright 2024')));}
function handleClick(){alert('Clicked!');}
const root=document.getElementById('root');ReactDOM.createRoot(root).render(e(App));"""
    html_2b = f"""<!DOCTYPE html>
<html><head><title>React App</title></head>
<body><div id="root"></div>
<script>{react_like}</script></body></html>"""
    run_and_check("2b: Minified React-like output", html_2b)

    # 2c: AI-generated single-page app
    print("  [2c] AI-generated SPA...")
    spa_js = """const state={todos:[],filter:'all'};
function addTodo(t){state.todos.push({id:Date.now(),text:t,done:false});render();}
function toggleTodo(id){const t=state.todos.find(t=>t.id===id);if(t)t.done=!t.done;render();}
function deleteTodo(id){state.todos=state.todos.filter(t=>t.id!==id);render();}
function render(){const list=document.getElementById('todo-list');if(!list)return;
list.innerHTML='';state.todos.filter(t=>state.filter==='all'||
(state.filter==='active'&&!t.done)||(state.filter==='done'&&t.done))
.forEach(t=>{const li=document.createElement('li');
li.innerHTML=`<input type="checkbox"${t.done?' checked':''}><span>${t.text}</span>
<button onclick="deleteTodo(${t.id})">×</button>`;list.appendChild(li);});}
document.getElementById('add-btn').addEventListener('click',function(){
const input=document.getElementById('todo-input');if(input&&input.value.trim()){addTodo(input.value.trim());input.value='';}});
document.querySelectorAll('.filter-btn').forEach(btn=>btn.addEventListener('click',function(){
state.filter=this.dataset.filter;document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
this.classList.add('active');render();}));"""
    html_2c = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>My Todo App</title></head>
<body>
<div id="app"><h1>Todo App</h1>
<input id="todo-input" type="text" placeholder="Add todo...">
<button id="add-btn">Add</button>
<div><button class="filter-btn active" data-filter="all">All</button>
<button class="filter-btn" data-filter="active">Active</button>
<button class="filter-btn" data-filter="done">Done</button></div>
<ul id="todo-list"></ul></div>
<script>{spa_js}
render();</script></body></html>"""
    run_and_check("2c: AI-generated SPA HTML", html_2c)


# ============================================================
# SECTION 3: TypeScript/JSX in scripts
# ============================================================

def test_3_ts_jsx():
    """TS/JSX syntax that AI might accidentally include."""
    print("\n# [3] TypeScript/JSX in scripts")

    # 3a: JSX in script
    jsx_code = """const element = <div className="app">
  <h1>Hello, world!</h1>
  <p>This is JSX</p>
</div>;
function Button(props) {
  return <button onClick={props.onClick}>{props.label}</button>;
}
const App = () => (
  <div>
    <Button label="Click" onClick={() => alert('hi')} />
  </div>
);"""
    run_and_check("3a: JSX syntax in script",
                  f"<html><body><script>{jsx_code}</script></body></html>")

    # 3b: TypeScript type annotations
    ts_code = """interface User {
  id: number;
  name: string;
  email: string;
}
type Status = 'active' | 'inactive' | 'pending';
function greet(user: User): string {
  return `Hello, ${user.name}!`;
}
const count: number = 42;
let items: string[] = ['a', 'b', 'c'];
function process(data: Record<string, number>): void {
  Object.keys(data).forEach(k => console.log(k));
}
function identity<T>(arg: T): T {
  return arg;
}
const result = identity<string>('hello');"""
    run_and_check("3b: TypeScript type annotations",
                  f"<html><body><script>{ts_code}</script></body></html>")

    # 3c: Mixed JS/TS with const assertions and decorators
    mixed_ts = """const x = { name: 'test' } as const;
type DeepPartial<T> = { [P in keyof T]?: DeepPartial<T[P]> };
@observer
class MyComponent {
  @observable count = 0;
  @action increment() {
    this.count++;
  }
  render() {
    return <div>{this.count}</div>;
  }
}"""
    run_and_check("3c: TypeScript decorators + assertions",
                  f"<html><body><script>{mixed_ts}</script></body></html>")


# ============================================================
# SECTION 4: Async complexity
# ============================================================

def test_4_async():
    """Async complexity tests."""
    print("\n# [4] Async Complexity")

    # 4a: Deep Promise chain (10+ levels)
    promise_chain = """function step1() { return Promise.resolve(1); }
function step2(n) { return Promise.resolve(n + 1); }
function step3(n) { return Promise.resolve(n * 2); }
function step4(n) { return Promise.resolve(n - 1); }
function step5(n) { return Promise.resolve(n * 3); }
function step6(n) { return Promise.resolve(n / 2); }
function step7(n) { return Promise.resolve(n + 10); }
function step8(n) { return Promise.resolve(n - 5); }
function step9(n) { return Promise.resolve(n * 1.5); }
function step10(n) { return Promise.resolve(Math.floor(n)); }
function step11(n) { return Promise.resolve(n + 100); }
function step12(n) { return Promise.resolve(n - 50); }

step1()
  .then(step2).then(step3).then(step4).then(step5)
  .then(step6).then(step7).then(step8).then(step9)
  .then(step10).then(step11).then(step12)
  .then(function(result) {
    console.log('Final:', result);
  })
  .catch(function(err) {
    console.error('Error:', err);
  });"""
    run_and_check("4a: Deep Promise chain (12 levels)",
                  f"<html><body><script>{promise_chain}</script></body></html>")

    # 4b: async/await with error handling
    async_code = """async function fetchData(url) {
  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error('HTTP error ' + response.status);
    }
    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Fetch failed:', error);
    return null;
  }
}
async function processItems(items) {
  const results = [];
  for (const item of items) {
    try {
      const result = await processItem(item);
      results.push(result);
    } catch (e) {
      console.error('Item failed:', item, e);
    }
  }
  return results;
}
async function main() {
  const data = await fetchData('/api/data');
  const processed = await processItems(data || []);
  console.log('Done:', processed);
}
main().catch(e => console.error('Fatal:', e));"""
    run_and_check("4b: async/await with error handling",
                  f"<html><body><script>{async_code}</script></body></html>")

    # 4c: try/catch/finally blocks
    try_code = """function riskyOperation(input) {
  let result;
  try {
    console.log('Starting operation with', input);
    if (input < 0) {
      throw new Error('Negative input not allowed');
    }
    result = 100 / input;
    console.log('Result:', result);
  } catch (error) {
    console.error('Operation failed:', error.message);
    result = -1;
  } finally {
    console.log('Operation completed');
    cleanup();
  }
  return result;
}
function nestedTry(x) {
  try {
    try {
      try {
        if (x === 0) throw new Error('Zero');
        return 1 / x;
      } catch (e) {
        throw new Error('Inner: ' + e.message);
      }
    } catch (e) {
      throw new Error('Middle: ' + e.message);
    }
  } catch (e) {
    console.error('Outer:', e.message);
    return 0;
  }
}
function cleanup() {
  console.log('Cleanup done');
}"""
    run_and_check("4c: try/catch/finally blocks",
                  f"<html><body><script>{try_code}</script></body></html>")

    # 4d: Callback hell (nested callbacks)
    callback_hell = """function first(callback) {
  setTimeout(function() {
    console.log('First done');
    callback(null, 'result1');
  }, 100);
}
function second(arg, callback) {
  setTimeout(function() {
    console.log('Second done with', arg);
    callback(null, 'result2');
  }, 100);
}
function third(arg, callback) {
  setTimeout(function() {
    console.log('Third done with', arg);
    callback(null, 'result3');
  }, 100);
}
function fourth(arg, callback) {
  setTimeout(function() {
    console.log('Fourth done with', arg);
    callback(null, 'result4');
  }, 100);
}
function fifth(arg, callback) {
  setTimeout(function() {
    console.log('Fifth done with', arg);
    callback(null, 'final_result');
  }, 100);
}
// Callback hell
first(function(err, res1) {
  if (err) return console.error(err);
  second(res1, function(err, res2) {
    if (err) return console.error(err);
    third(res2, function(err, res3) {
      if (err) return console.error(err);
      fourth(res3, function(err, res4) {
        if (err) return console.error(err);
        fifth(res4, function(err, final) {
          if (err) return console.error(err);
          console.log('Final:', final);
        });
      });
    });
  });
});"""
    run_and_check("4d: Callback hell (nested 5 levels)",
                  f"<html><body><script>{callback_hell}</script></body></html>")


# ============================================================
# SECTION 5: Module scripts
# ============================================================

def test_5_modules():
    """Module script tests."""
    print("\n# [5] Module Scripts")

    # 5a: type="module" with import/export
    module_code = """import { createApp } from './app.js';
import { reactive, computed } from './reactivity.js';
import { mount, render } from './dom.js';

const App = {
  template: '<div>{{ message }}</div>',
  setup() {
    const state = reactive({ message: 'Hello Vue!' });
    return { ...state };
  }
};

const app = createApp(App);
app.mount('#app');

export default App;"""
    run_and_check("5a: type=module with import/export",
                  f"<html><body><script type=\"module\">{module_code}</script></body></html>")

    # 5b: Dynamic imports
    dynamic_import = """async function loadModule() {
  try {
    const module = await import('./dynamic.js');
    const data = await import('./data.json', { assert: { type: 'json' } });
    const utils = await import(/* webpackChunkName: 'utils' */ './utils.js');
    module.default();
    console.log('Data:', data.default);
    return utils.helper();
  } catch (error) {
    console.error('Failed to load module:', error);
  }
}
const button = document.getElementById('load-btn');
button.addEventListener('click', async () => {
  const { format } = await import('./formatters.js');
  const result = format('Hello');
  console.log(result);
});"""
    run_and_check("5b: Dynamic import() calls",
                  f"<html><body><script>{dynamic_import}</script></body></html>")

    # 5c: Mixed module patterns
    mixed_modules = """import defaultExport, { named1, named2 as alias } from './module.js';
import * as namespace from './namespace.js';
export { defaultExport, alias };
export const x = 1;
export function y() { return 2; }
export class Z {}
export { default as Default } from './fallback.js';"""
    run_and_check("5c: Mixed import/export patterns",
                  f"<html><body><script type=\"module\">{mixed_modules}</script></body></html>")


# ============================================================
# SECTION 6: Property access edge cases
# ============================================================

def test_6_property_access():
    """Property access edge cases."""
    print("\n# [6] Property Access Edge Cases")

    # 6a: Bracket notation with variables
    bracket = """const obj = { a: 1, b: 2, c: 3 };
const key = 'b';
const val = obj[key];
const nested = { data: { items: [{ id: 1 }, { id: 2 }] } };
const dynamicKey = 'items';
const firstItem = nested.data[dynamicKey][0];
for (let k in obj) {
  console.log(k, obj[k]);
}
const keys = ['a', 'b', 'c'];
keys.forEach(k => console.log(obj[k]));"""
    run_and_check("6a: Bracket notation with variables",
                  f"<html><body><script>{bracket}</script></body></html>")

    # 6b: Nested property access
    nested_props = """const config = {
  server: {
    host: 'localhost',
    port: 8080,
    auth: {
      token: 'abc123',
      type: 'bearer'
    }
  },
  features: {
    darkMode: true,
    notifications: {
      sound: true,
      desktop: false
    }
  }
};
const host = config.server.host;
const port = config.server.port;
const token = config.server.auth.token;
const sound = config.features.notifications.sound;
console.log(host, port, token, sound);"""
    run_and_check("6b: Nested property access",
                  f"<html><body><script>{nested_props}</script></body></html>")

    # 6c: Optional chaining
    optional_chaining = """const user = {
  name: 'Alice',
  address: {
    street: '123 Main St'
  }
};
const street = user?.address?.street;
const zip = user?.address?.zip ?? 'N/A';
const phone = user?.contact?.phone ?? 'No phone';
const deep = data?.results?.[0]?.items?.map?.(x => x.name) ?? [];
const optionalCall = obj?.method?.();
console.log(street, zip, phone);"""
    run_and_check("6c: Optional chaining (?.)",
                  f"<html><body><script>{optional_chaining}</script></body></html>")

    # 6d: Nullish coalescing
    nullish = """const a = null ?? 'default';
const b = undefined ?? 'default';
const c = 0 ?? 'default';
const d = '' ?? 'default';
const e = false ?? 'default';
const f = null ?? undefined ?? 'fallback';
const g = (null ?? 0) ?? 'nope';
console.log(a, b, c, d, e, f, g);"""
    run_and_check("6d: Nullish coalescing (??)",
                  f"<html><body><script>{nullish}</script></body></html>")


# ============================================================
# SECTION 7: Real-world AI bug patterns
# ============================================================

def test_7_ai_bug_patterns():
    """Real-world AI bug patterns."""
    print("\n# [7] Real-World AI Bug Patterns")

    # 7a: Duplicate IDs in HTML
    dup_ids = """<!DOCTYPE html>
<html><body>
<div id="app">First</div>
<div id="app">Second</div>
<div id="submit-btn">Button</div>
<div id="submit-btn">Another</div>
<script>
const app = document.getElementById('app');
const btn = document.getElementById('submit-btn');
</script>
</body></html>"""
    run_and_check("7a: Duplicate IDs in HTML", dup_ids)

    # 7b: Case typos in getElementById
    case_typos = """<!DOCTYPE html>
<html><body>
<div id="myDiv">Content</div>
<script>
// Correct casing
document.getElementById('myDiv');
// Wrong casing
document.getElementById('MyDiv');
document.getElementById('mydiv');
// Variations
document.getElementById('MYDIV');
document.getElementById('mydiV');
</script>
</body></html>"""
    run_and_check("7b: Case typos in getElementById", case_typos)

    # 7c: Mixing getElementById with querySelector mismatch
    selector_mismatch = """<!DOCTYPE html>
<html><body>
<div id="my-id">Div 1</div>
<div class="my-class">Div 2</div>
<p id="my-id">Paragraph with same id</p>
<script>
const el1 = document.getElementById('my-id');
const el2 = document.querySelector('#my-id');
const el3 = document.querySelector('.my-class');
const el4 = document.getElementById('my-class'); // wrong — class not id
const el5 = document.querySelector('#nonexistent');
</script>
</body></html>"""
    run_and_check("7c: getElementById/querySelector mismatch", selector_mismatch)

    # 7d: Inline onclick + addEventListener conflict
    onclick_conflict = """<!DOCTYPE html>
<html><body>
<button id="btn1" onclick="handleClick()">Button 1</button>
<button id="btn2" onclick="handleClick()">Button 2</button>
<script>
function handleClick() {
  console.log('Clicked!');
  return false;
}
// This overrides the inline handler
document.getElementById('btn1').addEventListener('click', function(e) {
  console.log('From addEventListener');
  e.preventDefault();
});
// This ALSO adds a listener
document.getElementById('btn1').addEventListener('click', function() {
  console.log('Second listener');
});
</script>
</body></html>"""
    run_and_check("7d: Inline onclick + addEventListener conflict", onclick_conflict)

    # 7e: Functions declared but never called
    uncalled_funcs = """<!DOCTYPE html>
<html><body>
<script>
function initApp() {
  console.log('Initializing...');
}
function loadData() {
  fetch('/api/data');
}
function renderUI() {
  const app = document.getElementById('app');
  app.innerHTML = '<h1>Hello</h1>';
}
function handleError(err) {
  console.error('Error:', err);
}
// Only initApp is called
initApp();
</script>
</body></html>"""
    run_and_check("7e: Functions declared but never called", uncalled_funcs)

    # 7f: Variables assigned but never used
    unused_vars = """<!DOCTYPE html>
<html><body>
<script>
const apiKey = 'sk-123456789';
const secret = 'super-secret-value';
const config = {
  url: 'https://api.example.com',
  timeout: 5000
};
let counter = 0;
let debugMode = true;
// Only apiKey is used
console.log('Starting with key:', apiKey);
</script>
</body></html>"""
    run_and_check("7f: Variables assigned but never used", unused_vars)

    # 7g: console.log('error') vs console.error('error')
    log_vs_error = """<!DOCTYPE html>
<html><body>
<script>
function handleError(err) {
  // AI mistakenly uses console.log for errors
  console.log('Error occurred:', err.message);
  console.log('Stack trace:', err.stack);
}
function handleWarning(warn) {
  console.warn('Warning:', warn);
}
function handleSuccess(msg) {
  console.log('Success:', msg);
}
// Proper error logging
try {
  throw new Error('Test error');
} catch (e) {
  console.error('Caught:', e);
  handleError(e);
}
</script>
</body></html>"""
    run_and_check("7g: console.log('error') vs console.error() confusion", log_vs_error)


# ============================================================
# SECTION 8: File system edge cases
# ============================================================

def test_8_filesystem():
    """File system edge cases."""
    print("\n# [8] File System Edge Cases")

    base_html = "<html><body><script>let x=1;</script></body></html>"

    # 8a: File with spaces in name
    print("  [8a] File with spaces in name...")
    path_spaces = os.path.join(tempfile.gettempdir(), "my file.html")
    try:
        with open(path_spaces, 'w') as f:
            f.write(base_html)
        result = run_cli(path_spaces)
        _analyze("8a: File with spaces in name", result, expected_fail=False)
        os.unlink(path_spaces)
    except Exception as e:
        record_issue("minor", "filesystem", "8a: File with spaces in name",
                     f"Could not create file: {e}")

    # 8b: File with unicode in name
    print("  [8b] File with unicode in name...")
    path_unicode = os.path.join(tempfile.gettempdir(), "über cool.html")
    try:
        with open(path_unicode, 'w') as f:
            f.write(base_html)
        result = run_cli(path_unicode)
        _analyze("8b: File with unicode in name ('über cool')", result, expected_fail=False)
        os.unlink(path_unicode)
    except Exception as e:
        record_issue("minor", "filesystem", "8b: File with unicode in name",
                     f"Could not create file: {e}")

    # 8c: Symlink to a file
    print("  [8c] Symlink to a file...")
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write(base_html)
        real_path = f.name
    symlink_path = os.path.join(tempfile.gettempdir(), "symlink_test.html")
    try:
        if os.path.exists(symlink_path):
            os.unlink(symlink_path)
        os.symlink(real_path, symlink_path)
        result = run_cli(symlink_path)
        _analyze("8c: Symlink to HTML file", result, expected_fail=False)
        os.unlink(symlink_path)
    except OSError as e:
        record_issue("minor", "filesystem", "8c: Symlink to file",
                     f"Could not create symlink: {e}")
    os.unlink(real_path)

    # 8d: Directory with nested subdirectories and mixed file types
    print("  [8d] Nested directory with mixed files...")
    test_dir = os.path.join(tempfile.gettempdir(), "stress_test_dir_" + str(random.randint(10000, 99999)))
    try:
        os.makedirs(test_dir, exist_ok=True)
        os.makedirs(os.path.join(test_dir, "sub1"), exist_ok=True)
        os.makedirs(os.path.join(test_dir, "sub2", "deep"), exist_ok=True)

        # .html files that should be found
        files = {
            "index.html": "<html><body><script>let x=1;</script></body></html>",
            "sub1/page.html": "<html><body><script>let y=2;</script></body></html>",
            "sub2/deep/other.html": "<html><body><p>No script here</p></body></html>",
        }
        # Non-.html files that should be ignored
        non_html = {
            "style.css": "body { color: red; }",
            "app.js": "console.log('hello');",
            "sub1/data.json": '{"key": "value"}',
            "sub2/readme.txt": "This is a text file.",
            "sub2/deep/note.md": "# Markdown file",
        }

        for relpath, content in {**files, **non_html}.items():
            full = os.path.join(test_dir, relpath)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'w') as f:
                f.write(content)

        result = run_cli(test_dir)
        _analyze("8d: Nested dir with mixed file types", result, expected_fail=False)

        shutil.rmtree(test_dir, ignore_errors=True)
    except Exception as e:
        record_issue("minor", "filesystem", "8d: Nested directory",
                     f"Error: {e}")


# ============================================================
# SECTION 9: Encoding attacks
# ============================================================

def test_9_encoding():
    """Encoding attacks."""
    print("\n# [9] Encoding Attacks")

    # 9a: UTF-16 LE file with BOM
    print("  [9a] UTF-16 LE with BOM...")
    path_utf16le = os.path.join(tempfile.gettempdir(), "utf16le.html")
    try:
        html_content = "<html><body><script>let x=1;</script></body></html>"
        with open(path_utf16le, 'wb') as f:
            f.write(b'\xff\xfe')  # UTF-16 LE BOM
            f.write(html_content.encode('utf-16-le'))
        result = run_cli(path_utf16le)
        # Should handle or gracefully error (not crash)
        if result.get("exception") or "Traceback" in result.get("stderr", ""):
            record_issue("critical", "encoding", "9a: UTF-16 LE with BOM",
                         "Crashed on UTF-16 LE file", result.get("stderr", "")[:300])
        elif result["exit_code"] not in (0, 1):
            record_issue("moderate", "encoding", "9a: UTF-16 LE with BOM",
                         f"Unexpected exit code {result['exit_code']}")
        else:
            print(f"    Exit: {result['exit_code']}, No crash — handled gracefully")
        os.unlink(path_utf16le)
    except Exception as e:
        record_issue("minor", "encoding", "9a: UTF-16 LE with BOM",
                     f"Could not create file: {e}")

    # 9b: UTF-16 BE file with BOM
    print("  [9b] UTF-16 BE with BOM...")
    path_utf16be = os.path.join(tempfile.gettempdir(), "utf16be.html")
    try:
        html_content = "<html><body><script>let x=1;</script></body></html>"
        with open(path_utf16be, 'wb') as f:
            f.write(b'\xfe\xff')  # UTF-16 BE BOM
            f.write(html_content.encode('utf-16-be'))
        result = run_cli(path_utf16be)
        if result.get("exception") or "Traceback" in result.get("stderr", ""):
            record_issue("critical", "encoding", "9b: UTF-16 BE with BOM",
                         "Crashed on UTF-16 BE file", result.get("stderr", "")[:300])
        elif result["exit_code"] not in (0, 1):
            record_issue("moderate", "encoding", "9b: UTF-16 BE with BOM",
                         f"Unexpected exit code {result['exit_code']}")
        else:
            print(f"    Exit: {result['exit_code']}, No crash — handled gracefully")
        os.unlink(path_utf16be)
    except Exception as e:
        record_issue("minor", "encoding", "9b: UTF-16 BE with BOM",
                     f"Could not create file: {e}")

    # 9c: Latin-1 encoded file with accented characters
    print("  [9c] Latin-1 with accented characters...")
    path_latin1 = os.path.join(tempfile.gettempdir(), "latin1.html")
    try:
        # Latin-1 characters that aren't valid UTF-8
        latin1_bytes = b'<html><body><script>let caf\xe9 = 1; let \xe0\xe1\xe2 = 2;</script></body></html>'
        with open(path_latin1, 'wb') as f:
            f.write(latin1_bytes)
        result = run_cli(path_latin1)
        if result.get("exception") or "Traceback" in result.get("stderr", ""):
            record_issue("critical", "encoding", "9c: Latin-1 file",
                         "Crashed on Latin-1 file", result.get("stderr", "")[:300])
        elif result["exit_code"] not in (0, 1):
            record_issue("moderate", "encoding", "9c: Latin-1 file",
                         f"Unexpected exit code {result['exit_code']}")
        else:
            print(f"    Exit: {result['exit_code']}, No crash — handled gracefully")
        os.unlink(path_latin1)
    except Exception as e:
        record_issue("minor", "encoding", "9c: Latin-1 file",
                     f"Could not create file: {e}")

    # 9d: Mixed encoding declarations (meta charset says UTF-8 but file is Latin-1)
    print("  [9d] Mixed encoding declarations...")
    html_mixed = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">
</head>
<body>
<script>
let café = 1;  // Latin-1 chars in "UTF-8" declared file
</script>
</body>
</html>"""
    path_mixed = os.path.join(tempfile.gettempdir(), "mixed_encoding.html")
    try:
        with open(path_mixed, 'w', encoding='utf-8') as f:
            f.write(html_mixed)
        result = run_cli(path_mixed)
        _analyze("9d: Mixed encoding declarations", result, expected_fail=False)
        os.unlink(path_mixed)
    except Exception as e:
        record_issue("minor", "encoding", "9d: Mixed encoding declarations",
                     f"Error: {e}")


# ============================================================
# SECTION 10: Spec fulfillment edge cases
# ============================================================

def test_10_spec_fulfillment():
    """Spec fulfillment edge cases."""
    print("\n# [10] Spec Fulfillment Edge Cases")

    base_html = """<!DOCTYPE html>
<html><body>
<h1 id="title">Welcome to the Todo App</h1>
<p id="description">A simple application for managing tasks</p>
<input id="todo-input" type="text" placeholder="Enter a task">
<button id="add-btn">Add Task</button>
<ul id="todo-list"></ul>
<script>
function initApp() {
  const input = document.getElementById('todo-input');
  const addBtn = document.getElementById('add-btn');
  const list = document.getElementById('todo-list');
  addBtn.addEventListener('click', function() {
    const text = input.value.trim();
    if (text) {
      const li = document.createElement('li');
      li.textContent = text;
      list.appendChild(li);
      input.value = '';
    }
  });
}
function deleteTask(id) {
  // Remove task from list
}
initApp();
</script>
</body></html>"""

    # 10a: Very long spec (1000+ words)
    print("  [10a] Very long spec (1000+ words)...")
    long_spec = "# Todo Application Specification\n\n"
    long_spec += "## Overview\nThe Todo App should allow users to manage tasks.\n\n"
    words = ["user", "interface", "application", "task", "management", "todo", "list",
             "input", "button", "click", "add", "delete", "remove", "edit", "update",
             "save", "load", "data", "persist", "storage", "localStorage", "browser",
             "frontend", "backend", "API", "request", "response", "JSON", "REST",
             "design", "responsive", "mobile", "desktop", "CSS", "HTML", "JavaScript",
             "feature", "functionality", "requirement", "specification", "documentation",
             "component", "module", "service", "route", "navigation", "state", "props",
             "event", "handler", "callback", "promise", "async", "await", "fetch"]

    # Build a 1000+ word spec
    for i in range(100):
        long_spec += "## Section " + str(i + 1) + "\n\n"
        for _ in range(10):
            sentence = ' '.join(random.choice(words) for _ in range(random.randint(5, 15)))
            long_spec += sentence + ". "
        long_spec += "\n\n"

    path_spec = os.path.join(tempfile.gettempdir(), "long_spec.md")
    with open(path_spec, 'w') as f:
        f.write(long_spec)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write(base_html)
        html_path = f.name

    result = run_cli(html_path, ["--spec", path_spec])
    if result.get("exception") or "Traceback" in result.get("stderr", ""):
        record_issue("critical", "spec", "10a: Very long spec",
                     "Crashed with long spec", result.get("stderr", "")[:300])
    elif result.get("timed_out"):
        record_issue("critical", "spec", "10a: Very long spec",
                     "Timed out processing long spec")
    else:
        word_count = len(long_spec.split())
        print(f"    Spec length: {len(long_spec)} chars, ~{word_count} words")
        _analyze("10a: Very long spec", result)
    os.unlink(path_spec)
    os.unlink(html_path)

    # 10b: Spec with code blocks, headers, lists (markdown)
    print("  [10b] Markdown-heavy spec...")
    md_spec = """# Todo App Spec

## Requirements

### 1. Core Functionality

The application **must**:
- [ ] Allow users to *add* tasks
- [ ] Allow users to **delete** tasks
- [ ] Display a list of tasks

### 2. Technical Requirements

```javascript
// This is a code example
function addTask(text) {
    const task = { id: Date.now(), text, done: false };
    tasks.push(task);
    render();
}
```

> Note: This is a blockquote

| Feature | Priority | Status |
|---------|----------|--------|
| Add task | High | Done |
| Delete task | High | Pending |

#### Nested Header

1. First item
2. Second item
   - Sub-item
   - Another sub-item

Inline `code` and **bold** and *italic* and ~~strikethrough~~.

```html
<div id="app">
  <input type="text">
  <button>Add</button>
</div>
```
"""
    path_md_spec = os.path.join(tempfile.gettempdir(), "md_spec.md")
    with open(path_md_spec, 'w') as f:
        f.write(md_spec)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write(base_html)
        html_path2 = f.name

    result = run_cli(html_path2, ["--spec", path_md_spec])
    _analyze("10b: Markdown-heavy spec", result)
    os.unlink(path_md_spec)
    os.unlink(html_path2)

    # 10c: Partial keyword matches (spec keywords that partially match JS identifiers)
    print("  [10c] Partial keyword matching...")
    partial_spec = "# App Test\n\nThis application has: tasks, task management, user interface, button clicking, list rendering, input handling, event listening, todo management, data persistence, storage management, initialization process, app startup, deletion function, addition function, UI rendering, DOM manipulation, element creation, text content, value trimming, click handlers, event listeners.\n"
    path_partial = os.path.join(tempfile.gettempdir(), "partial_spec.md")
    with open(path_partial, 'w') as f:
        f.write(partial_spec)

    partial_html = """<!DOCTYPE html>
<html><body>
<script>
function manageTasks() { /* manages tasks */ }
function renderList() { /* renders list */ }
function handleInput() { /* handles input */ }
function startApp() { /* starts app */ }
const storage = {};
const manager = { process: function() {} };
</script>
</body></html>"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write(partial_html)
        html_path3 = f.name

    result = run_cli(html_path3, ["--spec", path_partial])
    _analyze("10c: Partial keyword matching", result)
    os.unlink(path_partial)
    os.unlink(html_path3)

    # 10d: Case sensitivity of keywords
    print("  [10d] Case sensitivity of keywords...")
    case_specs = [
        ("UPPERCASE spec", "TODO APP TASK MANAGEMENT DELETE BUTTON"),
        ("lowercase spec", "todo app task management delete button"),
        ("Mixed Case spec", "Todo App Task Management Delete Button"),
        ("ALL CAPS spec", "TODO APP TASK MANAGEMENT DELETE BUTTON"),
    ]
    case_html = """<!DOCTYPE html>
<html><body>
<button id="deleteBtn">Delete</button>
<input id="todoInput" type="text">
<script>
function handleDelete() { return true; }
function manageTask() { return true; }
const app = document.getElementById('todoInput');
const btn = document.getElementById('deleteBtn');
</script>
</body></html>"""

    for case_name, spec_text in case_specs:
        path_case_spec = os.path.join(tempfile.gettempdir(), f"case_{case_name.replace(' ', '_')}.md")
        with open(path_case_spec, 'w') as f:
            f.write(spec_text)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(case_html)
            html_path_c = f.name
        result = run_cli(html_path_c, ["--spec", path_case_spec])
        _analyze(f"10d: Case sensitivity — {case_name}", result)
        os.unlink(path_case_spec)
        os.unlink(html_path_c)

    # 10e: Unicode keywords in spec
    print("  [10e] Unicode keywords in spec...")
    unicode_spec = "# 中文测试\n\n"
    unicode_spec += "这个应用应该支持：任务管理、用户界面、按钮点击、列表渲染、输入处理\n"
    unicode_spec += "关键词：添加、删除、更新、保存、加载、显示、隐藏\n"
    unicode_spec += "组件：标题、描述、输入框、按钮、列表\n"
    unicode_spec += "功能：初始化、渲染、处理、管理\n"
    unicode_html = """<!DOCTYPE html>
<html><body>
<h1 id="title">任务管理</h1>
<p id="description">管理你的任务</p>
<input id="todo-input" type="text" placeholder="添加任务">
<button id="add-btn">添加</button>
<ul id="todo-list"></ul>
<script>
function initApp() { console.log('初始化'); }
function renderList() { console.log('渲染'); }
function handleInput() { console.log('处理'); }
initApp();
</script>
</body></html>"""
    path_unicode_spec = os.path.join(tempfile.gettempdir(), "unicode_spec.md")
    with open(path_unicode_spec, 'w') as f:
        f.write(unicode_spec)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write(unicode_html)
        html_path_u = f.name
    result = run_cli(html_path_u, ["--spec", path_unicode_spec])
    _analyze("10e: Unicode keywords in spec", result)
    os.unlink(path_unicode_spec)
    os.unlink(html_path_u)


# ============================================================
# SUMMARY
# ============================================================

def print_summary():
    print("\n" + "=" * 70)
    print("  STRESS TEST ROUND 2 — FINAL RESULTS")
    print("=" * 70)

    critical = RESULTS["critical"]
    moderate = RESULTS["moderate"]
    minor = RESULTS["minor"]
    info = RESULTS["info"]

    print(f"\n  🔴 CRITICAL: {len(critical)}")
    for c in critical:
        print(f"    - [{c['test']}] {c['issue']}")
        if c['detail']:
            for line in c['detail'].split('\n')[:3]:
                print(f"      {line}")

    print(f"\n  🟡 MODERATE: {len(moderate)}")
    for m in moderate:
        print(f"    - [{m['test']}] {m['issue']}")
        if m['detail']:
            for line in m['detail'].split('\n')[:2]:
                print(f"      {line}")

    print(f"\n  🔵 MINOR: {len(minor)}")
    for m in minor:
        print(f"    - [{m['test']}] {m['issue']}")

    print(f"\n  ℹ️ INFO: {len(info)}")
    for i in info:
        print(f"    - [{i['test']}] {i['issue']}")

    print("\n" + "=" * 70)

    # Final Verdict
    print("\n  ## FINAL VERDICT")
    print()
    if len(critical) > 0:
        print(f"  🚨 NOT SAFE TO SHIP — {len(critical)} critical bug(s) found.")
    elif len(moderate) > 5:
        print(f"  ⚠️  NOT SAFE TO SHIP — {len(moderate)} moderate issues found (threshold exceeded).")
    elif len(moderate) > 0:
        print(f"  ⚠️  CONDITIONAL PASS — {len(moderate)} moderate issues should be addressed.")
    else:
        print(f"  ✅ SAFE TO SHIP — No critical issues found.")
    print()


if __name__ == "__main__":
    print("=" * 70)
    print("  MAESTRO-GUARD STRESS TEST ROUND 2")
    print("  Second-pass fuzzing and deep edge-case analysis")
    print("=" * 70)

    # Run ALL tests
    test_1_fuzzer()
    test_2_minified_code()
    test_3_ts_jsx()
    test_4_async()
    test_5_modules()
    test_6_property_access()
    test_7_ai_bug_patterns()
    test_8_filesystem()
    test_9_encoding()
    test_10_spec_fulfillment()

    # Summary
    print_summary()
