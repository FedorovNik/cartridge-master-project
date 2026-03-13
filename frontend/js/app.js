async function updateTable() {
    const response = await fetch('/api/v1/cartridges');
    const data = await response.json();
    const tbody = document.querySelector('#inv-table tbody');
    tbody.innerHTML = '';

    data.forEach(item => {
    const barcodes = item.barcodes.map(b => `<span class="barcode-badge">${b}</span>`).join('');
    
    // Передаем this в функцию changeQty.
    // Это позволит функции понять какая именно кнопка была нажата.
    const row = `<tr>
        <td>${item.id}</td>
        <td>${item.name}</td>
        <td class="test">
            <div class="qty-controls">
                <button class="qty-btn" onclick="changeQty(this, ${item.id}, -1)">-</button>
                <span class="qty-value">${item.quantity}</span>
                <button class="qty-btn" onclick="changeQty(this, ${item.id}, 1)">+</button>
            </div>
        </td>

        <td class="qty-min-require">
        ${item.min_qty}
        </td>

        <td>${barcodes}</td>

        <td>
            <span class="timedate_value">${item.last_update}</span>
        </td>
    </tr>`;
    
    tbody.innerHTML += row; 
});
}
async function changeQty(btn, cartridgeId, delta) {
    // Находим общую строку (tr), в которой находится нажатая кнопка
    const row = btn.closest('tr');
    // Ищем внутри этой строки элемент с количеством и элемент со временем
    const stockElement = row.querySelector('.qty-value');
    const timeElement = row.querySelector('.timedate_value');
    
    // Блокируем кнопку чтобы не было двойных кликов пока идет запрос
    btn.disabled = true;

    try {
        const response = await fetch(`/api/v1/cartridges/${cartridgeId}/stock`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ change: delta }) 
        });

        if (response.ok) {
            const data = await response.json();
            // Обновляем цифру количества
            stockElement.innerText = data.new_stock;
            // Обновляем время (проверяем, прислал ли сервер новое время, 
            // так как при уходе в минус сервер возвращает только new_stock)
            if (data.last_update) {
                timeElement.innerText = data.last_update;
            }
            else {
                console.error('Пусто');
            }
            
        } else {
            console.error('Ошибка при обновлении количества!');
            alert('Не удалось обновить базу данных!');
        }
    } catch (error) {
        console.error('Сетевая ошибка:', error);
    } finally {
        // Разблокируем кнопку
        btn.disabled = false;
    }
}
function filterTable() {
    // Получаем то, что ввел пользователь, и переводим в нижний регистр
    const searchValue = document.getElementById('searchInput').value.toLowerCase();
    
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
updateTable();
//setInterval(updateTable, 150000);