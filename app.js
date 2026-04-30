const statsGrid = document.getElementById("statsGrid");
const medicinesTable = document.getElementById("medicinesTable");
const lowStockList = document.getElementById("lowStockList");
const transactionsList = document.getElementById("transactionsList");
const suppliersList = document.getElementById("suppliersList");
const topDispensed = document.getElementById("topDispensed");
const receiveMedicineSelect = document.getElementById("receiveMedicineSelect");
const dispenseMedicineSelect = document.getElementById("dispenseMedicineSelect");
const toast = document.getElementById("toast");

const state = {
    medicines: [],
    visibleMedicines: [],
    suppliers: [],
    transactions: [],
    visibleTransactions: [],
};

async function fetchJSON(url, options = {}) {
    const response = await fetch(url, {
        headers: { "Content-Type": "application/json" },
        ...options,
    });
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error || "Something went wrong.");
    }
    return data;
}

function showToast(message, isError = false) {
    toast.textContent = message;
    toast.classList.remove("hidden");
    toast.classList.toggle("error", isError);
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => {
        toast.classList.add("hidden");
    }, 3000);
}

function renderStats(totals) {
    const items = [
        { label: "Medicines", value: totals.total_medicines, note: "Total medicine records" },
        { label: "Suppliers", value: totals.suppliers_count, note: "Registered suppliers" },
        { label: "Stock Units", value: totals.stock_units, note: "Units currently available" },
        { label: "Low Stock", value: totals.low_stock_items, note: "Items that need restocking" },
        { label: "Expiring Soon", value: totals.expiring_batches, note: "Batches expiring within 60 days" },
    ];

    statsGrid.innerHTML = items.map((item) => `
        <article class="stat-card">
            <p class="section-label">${item.label}</p>
            <h3>${item.value}</h3>
            <p>${item.note}</p>
        </article>
    `).join("");
}

function stockPill(status) {
    return `<span class="pill ${status.toLowerCase()}">${status}</span>`;
}

function prescriptionPill(medicine) {
    return medicine.requires_prescription
        ? '<span class="sub-pill rx">Rx Required</span>'
        : '<span class="sub-pill otc">OTC</span>';
}

function formatMoney(value) {
    return `Rs ${Number(value).toFixed(2)}`;
}

function formatDate(value) {
    return value ? value : "Not scheduled";
}

function renderMedicines(medicines) {
    medicinesTable.innerHTML = medicines.map((medicine) => `
        <tr>
            <td>
                <strong>${medicine.name}</strong>
                <div class="meta-line">${medicine.sku} · ${medicine.category_name}</div>
                <div class="meta-stack">${prescriptionPill(medicine)}</div>
            </td>
            <td>
                <strong>${medicine.supplier_name}</strong>
                <div class="meta-line">${formatMoney(medicine.unit_price)}</div>
            </td>
            <td>${medicine.dosage_form}</td>
            <td>
                <strong>${medicine.current_stock} units</strong>
                <div class="meta-line">Minimum stock ${medicine.reorder_level}</div>
                ${stockPill(medicine.stock_status)}
            </td>
            <td>${formatDate(medicine.nearest_expiry)}</td>
        </tr>
    `).join("") || '<tr><td colspan="5">No medicines match the current filters.</td></tr>';
}

function renderLowStock(items) {
    lowStockList.innerHTML = items.map((item) => `
        <div class="alert-item">
            <div>
                <strong>${item.name}</strong>
                <span>${item.current_stock} units left · minimum stock ${item.reorder_level}</span>
            </div>
            ${stockPill(item.stock_status)}
        </div>
    `).join("") || '<div class="alert-item">Inventory risk is currently under control.</div>';
}

function transactionPill(type) {
    return `<span class="pill ${type === "IN" ? "safe" : "out"}">${type === "IN" ? "Stock In" : "Dispensed"}</span>`;
}

function renderTransactions(items) {
    transactionsList.innerHTML = items.map((item) => `
        <div class="activity-item">
            <div>
                <strong>${item.medicine_name}</strong>
                <div class="meta-line">${item.batch_no || "No batch"} · ${item.quantity} units</div>
                <div class="meta-line">${item.reference_note || "No note"} · ${item.transaction_time}</div>
            </div>
            ${transactionPill(item.transaction_type)}
        </div>
    `).join("") || '<div class="activity-item">No stock activity found.</div>';
}

function renderSuppliers(items) {
    suppliersList.innerHTML = items.slice(0, 5).map((supplier) => `
        <div class="supplier-item">
            <div>
                <strong>${supplier.name}</strong>
                <span>${supplier.contact_person} · ${supplier.city}</span>
            </div>
            <span>${supplier.phone}</span>
        </div>
    `).join("") || '<div class="supplier-item">No suppliers added yet.</div>';
}

function renderTopDispensed(items) {
    const peak = Math.max(...items.map((item) => item.dispensed_units), 1);
    topDispensed.innerHTML = items.map((item) => `
        <div class="insight-row">
            <div>
                <strong>${item.name}</strong>
                <span>${item.dispensed_units} units dispensed</span>
            </div>
            <div class="bar-track">
                <div class="bar-fill" style="width: ${Math.max((item.dispensed_units / peak) * 100, item.dispensed_units ? 12 : 0)}%"></div>
            </div>
        </div>
    `).join("") || '<div class="insight-row">Dispense analytics will appear once transactions are recorded.</div>';
}

function fillMedicineOptions() {
    const options = state.medicines
        .map((medicine) => `<option value="${medicine.medicine_id}">${medicine.name} (${medicine.current_stock} units)</option>`)
        .join("");

    receiveMedicineSelect.innerHTML = '<option value="">Choose medicine</option>' + options;

    dispenseMedicineSelect.innerHTML = '<option value="">Choose medicine</option>' + state.medicines
        .filter((medicine) => medicine.current_stock > 0)
        .map((medicine) => `<option value="${medicine.medicine_id}">${medicine.name} (${medicine.current_stock} units)</option>`)
        .join("");
}

async function loadDashboard() {
    const data = await fetchJSON("/api/dashboard");
    renderStats(data.totals);
    renderLowStock(data.low_stock);
    renderTopDispensed(data.top_dispensed);
}

async function loadMedicines() {
    state.medicines = await fetchJSON("/api/medicines");
    applyMedicineFilters();
    fillMedicineOptions();
}

async function loadSuppliers() {
    state.suppliers = await fetchJSON("/api/suppliers");
    renderSuppliers(state.suppliers);
}

async function loadTransactions() {
    state.transactions = await fetchJSON("/api/transactions");
    applyTransactionFilters();
}

async function refreshAll() {
    await Promise.all([loadDashboard(), loadMedicines(), loadSuppliers(), loadTransactions()]);
}

function serialiseForm(form) {
    return Object.fromEntries(new FormData(form).entries());
}

function applyMedicineFilters() {
    const search = document.getElementById("medicineSearch").value.trim().toLowerCase();
    const stockFilter = document.getElementById("stockFilter").value;

    state.visibleMedicines = state.medicines.filter((medicine) => {
        const matchesSearch = !search || [
            medicine.name,
            medicine.sku,
            medicine.supplier_name,
            medicine.category_name,
        ].join(" ").toLowerCase().includes(search);

        const matchesFilter = stockFilter === "ALL" || medicine.stock_status === stockFilter;
        return matchesSearch && matchesFilter;
    });

    renderMedicines(state.visibleMedicines);
}

function applyTransactionFilters() {
    const type = document.getElementById("transactionFilter").value;
    state.visibleTransactions = state.transactions.filter((item) => type === "ALL" || item.transaction_type === type);
    renderTransactions(state.visibleTransactions);
}

async function handleSubmit(formId, url, afterReset) {
    const form = document.getElementById(formId);
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
            const payload = serialiseForm(form);
            await fetchJSON(url, {
                method: "POST",
                body: JSON.stringify(payload),
            });
            form.reset();
            if (afterReset) {
                afterReset(form);
            }
            await refreshAll();
            showToast("Operation completed successfully.");
        } catch (error) {
            showToast(error.message, true);
        }
    });
}

function setDefaultDates() {
    const today = new Date();
    const nextYear = new Date();
    nextYear.setFullYear(today.getFullYear() + 1);

    const receiveForm = document.getElementById("receiveForm");
    receiveForm.querySelector('input[name="received_on"]').value = today.toISOString().slice(0, 10);
    receiveForm.querySelector('input[name="manufacture_date"]').value = today.toISOString().slice(0, 10);
    receiveForm.querySelector('input[name="expiry_date"]').value = nextYear.toISOString().slice(0, 10);
}

document.getElementById("medicineSearch").addEventListener("input", applyMedicineFilters);
document.getElementById("stockFilter").addEventListener("change", applyMedicineFilters);
document.getElementById("transactionFilter").addEventListener("change", applyTransactionFilters);

handleSubmit("medicineForm", "/api/medicines");
handleSubmit("supplierForm", "/api/suppliers");
handleSubmit("receiveForm", "/api/stock/receive", setDefaultDates);
handleSubmit("dispenseForm", "/api/stock/dispense");

setDefaultDates();
refreshAll().catch((error) => showToast(error.message, true));
