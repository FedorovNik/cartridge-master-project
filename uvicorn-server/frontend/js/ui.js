/**
 * UI.JS
 * Функции для управления пользовательским интерфейсом (навигация, фильтрация)
 */

/**
 * Показывает нужную секцию и обновляет активное меню
 * @param {string} sectionId - ID секции для отображения
 * @param {HTMLElement} clickedBtn - кнопка меню, на которую нажали
 */
function showSection(sectionId, clickedBtn) {
    updateDashboard();
    // Скрываем все секции
    const sections = document.querySelectorAll('.content-section');
    sections.forEach(sec => sec.classList.remove('active-section'));

    // Убираем выделение (класс active) со всех кнопок меню
    const buttons = document.querySelectorAll('.nav-btn');
    buttons.forEach(btn => btn.classList.remove('active'));

    // Показываем нужную секцию
    document.getElementById(sectionId).classList.add('active-section');

    // Делаем нажатую кнопку активной
    clickedBtn.classList.add('active');
}

/**
 * Увеличивает/уменьшает значение в соседнем input[type=number] на 1
 * @param {HTMLElement} btn - кнопка +/-
 * @param {number} delta - изменение (+1 или -1)
 */
function adjustNumber(btn, delta) {
    const wrapper = btn.closest('.qty-controls');
    if (!wrapper) return;

    const input = wrapper.querySelector('input[type="number"]');
    if (!input) return;

    const current = parseInt(input.value, 10);
    if (Number.isNaN(current)) return;

    const next = current + delta;
    input.value = next < 0 ? 0 : next;
}

/**
 * Фильтрует таблицу "Список расходников" по названию
 * Вызывается при вводе текста в поле поиска
 */
function filterTable_list() {
    // Получаем то, что ввел пользователь, и переводим в нижний регистр
    const searchValue = document.getElementById('searchInput-1').value.toLowerCase();
    
    // Получаем все строки таблицы
    const rows = document.querySelectorAll('#inv-table tbody tr');

    rows.forEach(row => {
        // Берем конкретно вторую ячейку (td) в строке, где лежит имя
        const nameCell = row.cells[1]; 
        
        // На всякий случай проверяем, есть ли ячейка чтобы не было ошибок на пустых строках
        if (nameCell) {
            // Берем текст только из ячейки с именем
            const nameText = nameCell.textContent.toLowerCase();
            if (nameText.includes(searchValue)) {
                row.style.display = ''; 
            } else {
                row.style.display = 'none'; 
            }
        }
    });
}

/**
 * Фильтрует таблицу "Редактор БД" по названию
 * Вызывается при вводе текста в поле поиска
 */
function filterTable_edit() {
    // Получаем то, что ввел пользователь, и переводим в нижний регистр
    const searchValue = document.getElementById('searchInput-2').value.toLowerCase();
    
    // Получаем все строки таблицы
    const rows = document.querySelectorAll('#editor-table tbody tr');

    rows.forEach(row => {
        // Берем конкретно вторую ячейку (td) в строке, где лежит имя
        const nameCell = row.cells[1]; 
        
        // На всякий случай проверяем, есть ли ячейка чтобы не было ошибок на пустых строках
        if (nameCell) {
            // Для редактора имя в input, берем value
            const nameInput = nameCell.querySelector('input');
            const nameText = nameInput ? nameInput.value.toLowerCase() : '';
            if (nameText.includes(searchValue)) {
                row.style.display = ''; 
            } else {
                row.style.display = 'none'; 
            }
        }
    });
}
