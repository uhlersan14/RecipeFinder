// backend/static/js/script.js
document.addEventListener('DOMContentLoaded', () => {
    const ingredientsInput = document.getElementById('ingredients');
    const searchIngredientInput = document.getElementById('search_ingredient');

    // Beispiel: Großschreibung der ersten Buchstaben bei Eingabe
    ingredientsInput.addEventListener('input', (e) => {
        let value = e.target.value;
        value = value.split(',').map(item => {
            item = item.trim();
            return item.charAt(0).toUpperCase() + item.slice(1).toLowerCase();
        }).join(', ');
        e.target.value = value;
    });

    searchIngredientInput.addEventListener('input', (e) => {
        let value = e.target.value;
        value = value.charAt(0).toUpperCase() + value.slice(1).toLowerCase();
        e.target.value = value;
    });
});