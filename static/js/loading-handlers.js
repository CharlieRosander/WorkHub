// Function to show loading state
function showLoading(button) {
    const originalContent = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Loading...`;
    // Store the original content
    button.setAttribute('data-original-content', originalContent);
}

// Function to restore button state
function restoreButton(button) {
    const originalContent = button.getAttribute('data-original-content');
    if (originalContent) {
        button.innerHTML = originalContent;
        button.disabled = false;
    }
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
