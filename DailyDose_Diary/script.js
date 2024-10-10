function openTab(tabName) {
    const tabContents = document.querySelectorAll('.tab-content');
    tabContents.forEach(content => {
        content.style.display = 'none';
    });

    document.getElementById(tabName).style.display = 'block';
}

// Initialize the first tab as active
document.addEventListener('DOMContentLoaded', () => {
    openTab('food');
});

// Example form submission handling
document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', function(event) {
        event.preventDefault();
        const inputs = this.querySelectorAll('input');
        const itemName = inputs[0].value;
        const quantity = inputs[1] ? inputs[1].value : '';
        const listId = this.id.replace('Form', 'List');
        const itemList = document.getElementById(listId);
        const itemDiv = document.createElement('div');
        itemDiv.className = 'item';
        itemDiv.textContent = quantity ? `${itemName} - Quantity: ${quantity}` : itemName;
        itemList.appendChild(itemDiv);
        this.reset();
    });
});

document.getElementById('exportButton').addEventListener('click', async function() {
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF();

    // Collect data from each list
    const categories = ['food', 'medicine', 'supplements', 'skin-contact', 'miscellaneous'];
    let yOffset = 20;
    categories.forEach(category => {
        const list = document.getElementById(`${category}List`);
        const items = list.querySelectorAll('.item');
        if (items.length > 0) {
            doc.text(20, yOffset, category.charAt(0).toUpperCase() + category.slice(1));
            yOffset += 10;
            items.forEach((item, index) => {
                doc.text(20, yOffset + (index * 10), item.textContent);
            });
            yOffset += items.length * 10 + 10;
        }
    });

    // Save the PDF
    doc.save('health_tracker.pdf');

    // Optionally, send the PDF to the server for emailing
    // await sendPDFToServer(doc.output('blob'));
});

// Function to send PDF to server
async function sendPDFToServer(pdfBlob) {
    const formData = new FormData();
    formData.append('pdf', pdfBlob, 'health_tracker.pdf');
    formData.append('email', prompt('Enter your email address:'));

    const response = await fetch('/send-pdf', {
        method: 'POST',
        body: formData
    });

    if (response.ok) {
        alert('PDF sent to your email!');
    } else {
        alert('Failed to send PDF.');
    }
}