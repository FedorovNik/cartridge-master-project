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
        let qtyClass = 'qty-value';

        if (item.quantity < item.min_qty) {
            qtyClass += ' low-stock';
        } else if (item.quantity === item.min_qty) {
            qtyClass += ' equal-stock';
        }

        const row = `<tr>
            <td>${item.id}</td>
            <td>${item.name}</td>
            <td><span class="${qtyClass}">${item.quantity}</span></td>
            <td>${item.min_qty}</td>
            <td>${item.last_update}</td>
        </tr>`;
        tbody.innerHTML += row;
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
        const row = `<tr data-cartridge-id="${item.id}">
            <td>${item.id}</td>
            <td><input type="text" class="name-input" value="${item.name}" /></td>
            <td>
                <div class="qty-controls">
                    <button type="button" class="qty-btn" onclick="adjustNumber(this, -1)">-</button>
                    <input type="number" min="0" class="qty-input current-qty" value="${item.quantity}" />
                    <button type="button" class="qty-btn" onclick="adjustNumber(this, 1)">+</button>
                </div>
            </td>
            <td>
                <div class="qty-controls">
                    <button type="button" class="qty-btn" onclick="adjustNumber(this, -1)">-</button>
                    <input type="number" min="0" class="qty-input min-qty" value="${item.min_qty}" />
                    <button type="button" class="qty-btn" onclick="adjustNumber(this, 1)">+</button>
                </div>
            </td>
            <td><button type="button" class="save-btn" onclick="saveRow(this)">Сохранить</button></td>
            <td class="barcodes-cell" data-cartridge-id="${item.id}">
                ${item.barcodes.map(b => `<div class="barcode-item"><span class="barcode-badge">${b}</span><button type="button" class="remove-btn" onclick="removeBarcode(this, '${b}')">-</button></div>`).join('')}
                <div class="add-barcode"><input type="text" class="new-barcode-input" placeholder="Новый штрих-код"><button type="button" class="add-btn" onclick="addBarcode(this)">+</button></div>
            </td>
            <td><span class="timedate_value">${item.last_update}</span></td>
        </tr>`;
        tbody.innerHTML += row;
    });
}
