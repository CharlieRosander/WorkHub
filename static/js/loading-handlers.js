/**
 * Visar laddningsstatus för en knapp
 * @param {HTMLElement} button - Knappen som ska visa laddningsstatus
 * @param {string} [loadingText="Loading..."] - Text som visas under laddning
 */
function showLoading(button, loadingText = "Loading...") {
    // Spara originalinnehåll om det inte redan finns sparat
    if (!button.hasAttribute('data-original-content')) {
        button.setAttribute('data-original-content', button.innerHTML);
    }
    
    // Inaktivera knappen och visa laddningsindikator
    button.disabled = true;
    button.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>${loadingText}`;
    
    // Markera knappen som laddande
    button.setAttribute('data-loading', 'true');
}

/**
 * Återställer en knapp till sitt ursprungliga utseende
 * @param {HTMLElement} button - Knappen som ska återställas
 */
function restoreButton(button) {
    // Kontrollera om knappen har originalinnehåll sparat
    const originalContent = button.getAttribute('data-original-content');
    if (originalContent) {
        button.innerHTML = originalContent;
        button.disabled = false;
        button.removeAttribute('data-loading');
    }
}

/**
 * Ger visuell feedback genom att tillfälligt ändra knappens utseende
 * @param {HTMLElement} button - Knappen som ska få feedback
 * @param {string} feedbackType - Typ av feedback ("success" eller "error")
 * @param {number} [duration=1000] - Tid i millisekunder som feedbacken visas
 */
function giveButtonFeedback(button, feedbackType, duration = 1000) {
    // Kontrollera först om knappen fortfarande finns i DOM
    if (!document.body.contains(button)) return;
    
    // Ta bort eventuella tidigare feedback-klasser
    button.classList.remove('btn-success', 'btn-danger');
    
    // Spara knappens ursprungliga btn-klasser
    const originalClasses = Array.from(button.classList)
        .filter(cls => cls.startsWith('btn-'))
        .join(' ');
    
    // Applicera rätt feedbackklass baserat på typ
    if (feedbackType === 'success') {
        button.classList.add('btn-success');
    } else if (feedbackType === 'error') {
        button.classList.add('btn-danger');
    }
    
    // Lägg till en timer för att återställa knappens utseende
    setTimeout(() => {
        // Kontrollera igen om knappen fortfarande finns i DOM
        if (document.body.contains(button)) {
            // Ta bort feedback-klasserna
            button.classList.remove('btn-success', 'btn-danger');
            
            // Återställ originalklasserna
            originalClasses.split(' ').forEach(cls => {
                if (cls && cls.length > 0) button.classList.add(cls);
            });
        }
    }, duration);
}

// Handle scrape website form
document.addEventListener('DOMContentLoaded', function() {
    const scrapeForm = document.querySelector('form[action*="scrape_job_listing"]');
    if (scrapeForm) {
        scrapeForm.addEventListener('submit', function(e) {
            const button = this.querySelector('button[type="submit"]');
            showLoading(button);
        });
    }

    // Handle process with GPT forms
    const processGPTForms = document.querySelectorAll('form[action*="process_html"]');
    processGPTForms.forEach(form => {
        form.addEventListener('submit', function(e) {
            // Find the parent dropdown
            const dropdownContainer = this.closest('.dropdown');
            if (dropdownContainer) {
                // Get the main dropdown toggle button
                const mainButton = dropdownContainer.querySelector('.dropdown-toggle');
                if (mainButton) {
                    showLoading(mainButton);
                }
            }
        });
    });

    // Handle generate name form
    const generateNameForm = document.querySelector('form[action*="generate_filenames"]');
    if (generateNameForm) {
        generateNameForm.addEventListener('submit', function(e) {
            const button = this.querySelector('button[type="submit"]');
            showLoading(button);
        });
    }
});
