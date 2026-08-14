from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://job-boards.greenhouse.io/clickhouse/jobs/6014112004', wait_until='networkidle')
    
    # Check form method and action
    form = page.query_selector('form[action*="/jobs/"]')
    if form:
        print('Form method:', form.get_attribute('method'))
        print('Form action:', form.get_attribute('action'))
        print('Form enctype:', form.get_attribute('enctype'))
        
        # Check if form has onsubmit
        onsubmit = form.get_attribute('onsubmit')
        print('Form onsubmit:', onsubmit)
        
        # Check submit button
        submit = page.query_selector('button:has-text("Submit application")')
        if submit:
            in_form = page.evaluate('el => el.form !== null', submit)
            print('Submit in form:', in_form)
            
            # Check if form has onsubmit
            onsubmit = form.get_attribute('onsubmit')
            print('Form onsubmit:', onsubmit)
        
        # Check for JavaScript submit handlers
        has_js_handler = page.evaluate('''() => {
            const form = document.querySelector('form[action*="/jobs/"]');
            if (!form) return false;
            
            // Check for onsubmit
            if (form.onsubmit) return true;
            
            // Check for event listeners
            const listeners = getEventListeners ? getEventListeners(form) : {};
            return 'submit' in listeners;
        }''')
        print('Has JS submit handler:', page.evaluate('''() => {
            const form = document.querySelector('form[action*="/jobs/"]');
            if (!form) return false;
            return form.onsubmit !== null || (getEventListeners ? 'submit' in getEventListeners(form) : false);
        }'''))
        
        # Check submit button onclick
        has_click = page.evaluate('''() => {
            const btn = document.querySelector('button:has-text("Submit application")');
            return btn && btn.onclick !== null;
        }''')
        print('Submit button onclick:', page.evaluate('''() => {
            const btn = document.querySelector('button:has-text("Submit application")');
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