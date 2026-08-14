from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://job-boards.greenhouse.io/clickhouse/jobs/6014112004', wait_until='networkidle')
    
    # Check form details
    form = page.query_selector('form[action*="/jobs/"]')
    if form:
        print('Form method:', form.get_attribute('method'))
        print('Form action:', form.get_attribute('action'))
        print('Form enctype:', form.get_attribute('enctype'))
        print('Form onsubmit:', form.get_attribute('onsubmit'))
        
        # Check submit button
        submit = page.query_selector('button[type="submit"]')
        if submit:
            onclick = submit.get_attribute('onclick')
            print('Submit onclick:', onclick)
        
        # Check for event listeners
        has_listener = page.evaluate('''() => {
            const form = document.querySelector('form[action*="/jobs/"]');
            if (!form) return false;
            const listeners = getEventListeners ? getEventListeners(form) : {};
            return 'submit' in listeners;
        }''')
        print('Has submit listener:', page.evaluate('''() => {
            const form = document.querySelector('form[action*="/jobs/"]');
            if (!form) return false;
            const listeners = getEventListeners ? getEventListeners(form) : {};
            return 'submit' in listeners;
        }'''))
        
        # Check submit button onclick
        has_click = page.evaluate('''() => {
            const btn = document.querySelector('button[type="submit"]');
            return btn && btn.onclick !== null;
        }''')
        print('Submit button onclick:', page.evaluate('''() => {
            const btn = document.querySelector('button[type="submit"]');
            return btn && btn.onclick !== null;
        }'''))
        
        # Check for any form submit event listeners on document
        has_doc_listener = page.evaluate('''() => {
            const listeners = getEventListeners ? getEventListeners(document) : {};
            return 'submit' in listeners;
        }''')
        print('Document submit listeners:', page.evaluate('''() => {
            const listeners = getEventListeners ? getEventListeners(document) : {};
            return 'submit' in listeners;
        }'''))
    
    browser.close()