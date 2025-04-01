// static/js/script.js

document.addEventListener('DOMContentLoaded', function() {
    // Eventlistener für die "Details anzeigen" Buttons
    const detailButtons = document.querySelectorAll('.view-details-btn');
    detailButtons.forEach(button => {
        button.addEventListener('click', function() {
            const recipeId = this.getAttribute('data-recipe-id');
            // Hier könntest du eine AJAX-Anfrage machen, um weitere Details zu laden
            // oder ein Modal mit Details anzeigen
            alert(`Details für Rezept mit ID: ${recipeId} werden geladen...`);
            // In einer vollständigen Implementierung würdest du hier ein AJAX-Request machen
        });
    });

    // Automatisches Sortieren der Rezeptkarten nach Übereinstimmung
    const recipeList = document.querySelector('.recipe-list');
    if (recipeList) {
        // Die Karten sind bereits serverseitig sortiert, aber wir könnten
        // zusätzliche Client-seitige Sortierung implementieren, wenn gewünscht
    }

    // Verbesserte Zutateneingabe mit Komma-Trennung
    const ingredientsInput = document.getElementById('ingredients');
    if (ingredientsInput) {
        ingredientsInput.addEventListener('blur', function() {
            // Formatiere die Eingabe: Entferne doppelte Kommas, Leerzeichen vor/nach Kommas
            let value = this.value.trim();
            value = value.replace(/\s*,\s*/g, ', '); // Normalisiere Leerzeichen um Kommas
            value = value.replace(/,{2,}/g, ',');    // Entferne doppelte Kommas
            value = value.replace(/^,|,$/g, '');     // Entferne Kommas am Anfang und Ende
            this.value = value;
        });
    }

    // Optional: Animierte Farbübergänge bei den Übereinstimmungs-Badges
    const matchBadges = document.querySelectorAll('.match-badge');
    matchBadges.forEach(badge => {
        const matchPercentage = parseFloat(badge.textContent);
        if (matchPercentage >= 80) {
            badge.classList.remove('bg-primary');
            badge.classList.add('bg-success');
        } else if (matchPercentage < 50) {
            badge.classList.remove('bg-primary');
            badge.classList.add('bg-danger');
        } else if (matchPercentage < 70) {
            badge.classList.remove('bg-primary');
            badge.classList.add('bg-warning');
            badge.style.color = '#000'; // Dunkler Text für bessere Lesbarkeit auf gelbem Hintergrund
        }
    });
});