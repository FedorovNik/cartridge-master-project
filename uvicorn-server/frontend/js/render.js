/**
 * RENDER.JS
 * Функции для рендеринга HTML элементов и таблиц
 */

/**
 * Рендерит простой список картриджей с подсветкой критического остатка
 * @param {Array} data - массив картриджей из API
 */
function renderSimpleList(data) {
    const tbody = document.querySelector('#inv-table tbody');
    if (!tbody) return;
    
    tbody.innerHTML = '';
    data.forEach(item => {
        // Проверка: если количество меньше минимума — добавляем класс 'low-stock'
        const isLow = item.quantity < item.min_qty;
        const qtyClass = isLow ? 'qty-value low-stock' : 'qty-value';

        const row = `<tr>
            <td>${item.id}</td>
            <td>${item.name}</td>
            <td><span class="${qtyClass}">${item.quantity}</span></td>
            <td>${item.min_qty}</td>
            
            <td>${item.last_update}</td>
        </tr>`;
        tbody.innerHTML += row;
        //<td>${item.barcodes.map(b => `<span class="barcode-badge">${b}</span>`).join('')}</td>
    });
}

/**
 * Рендерит редактор списка картриджей с кнопками +/- для изменения количества
 * @param {Array} data - массив картриджей из API
 */
function renderEditorList(data) {
    const tbody = document.querySelector('#editor-table tbody');
    if (!tbody) return;

    tbody.innerHTML = '';
    data.forEach(item => {
        const row = `<tr>
            <td>${item.id}</td>
            <td>${item.name}</td>
            <td>
                <div class="qty-controls">
                    <button class="qty-btn" onclick="changeQty(this, ${item.id}, -1)">-</button>
                    <span class="qty-value">${item.quantity}</span>
                    <button class="qty-btn" onclick="changeQty(this, ${item.id}, 1)">+</button>
                </div>
            </td>
            <td>${item.min_qty}</td>
            <td>${item.barcodes.map(b => `<span class="barcode-badge">${b}</span>`).join('')}</td>
            <td><span class="timedate_value">${item.last_update}</span></td>
        </tr>`;
        tbody.innerHTML += row;
    });
}
