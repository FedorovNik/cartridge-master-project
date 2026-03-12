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
        <td>
            <div class="qty-controls">
                <button class="btn-dark" onclick="changeQty(this,${item.id}, -1)">-</button>
                <span class="stock-value">${item.quantity}</span>
                <button class="btn-dark" onclick="changeQty(this,${item.id}, 1)">+</button>
            </div>
        </td>
        <td>нет инфы</td>
        <td>${barcodes}</td>
        <td>${item.last_update}</td>
    </tr>`;
    
    tbody.innerHTML += row; 
});
}
async function changeQty(btn, cartridgeId, delta) {
    // Находим элемент где отображается количество
    const container = btn.closest('.qty-controls');
    const stockElement = container.querySelector('.stock-value');
    
    // Блокируем кнопку чтобы не было двойных кликов пока идет запрос
    btn.disabled = true;

    try {
        // Отправляем фоновый запрос к нашему API
        const response = await fetch(`/api/v1/cartridges/${cartridgeId}/stock`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ change: delta }) 
        });

        if (response.ok) {
            const data = await response.json();
            // Обновляем цифру на экране только ПОСЛЕ успешного ответа базы
            stockElement.innerText = data.new_stock;
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
updateTable();
setInterval(updateTable, 15000);