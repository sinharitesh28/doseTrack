
let compCount = 0; let diagCount = 0; let medCount = 0;
let consentPollInterval = null;

function setupAutocomplete(inputElement, idElement, type) {
    let timeout = null;
    const wrapper = document.createElement('div');
    wrapper.style.position = 'relative'; wrapper.style.flex = '1'; wrapper.style.minWidth = '200px';
    inputElement.parentNode.insertBefore(wrapper, inputElement);
    wrapper.appendChild(inputElement);

    const suggestionBox = document.createElement('div');
    suggestionBox.className = 'autocomplete-box';
    wrapper.appendChild(suggestionBox);

    document.addEventListener('click', function(e) {
        if (e.target !== inputElement) suggestionBox.style.display = 'none';
    });

    inputElement.addEventListener('input', function() {
        clearTimeout(timeout);
        const query = this.value;
        if (query.length < 3) { suggestionBox.style.display = 'none'; return; }

        timeout = setTimeout(async () => {
            try {
                let url = "";
                if (type === 'hpo') url = `https://clinicaltables.nlm.nih.gov/api/hpo/v3/search?terms=${query}`;
                if (type === 'icd10') url = `https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search?terms=${query}&sf=code,name`;
                if (type === 'rxterms') url = `https://clinicaltables.nlm.nih.gov/api/rxterms/v3/search?terms=${query}&ef=RXCUIS`;

                const response = await fetch(url);
                const data = await response.json();

                if (data[0] > 0) {
                    suggestionBox.innerHTML = ''; suggestionBox.style.display = 'block';

                    const array1 = data[1] || [];
                    const array2 = data[2] || {};
                    const array3 = data[3] || [];

                    array1.forEach((item1, index) => {
                        let termValue = "", idValue = "", displayText = "";

                        // Parse according to specific NLM API data structures
                        if (type === 'hpo') {
                            idValue = item1; // e.g., HP:0002018
                            termValue = (array3[index] && array3[index].length > 1) ? array3[index][1] : ""; 
                            displayText = `${termValue} (${idValue})`;
                        } 
                        else if (type === 'icd10') {
                            idValue = item1; // e.g., A00.9
                            termValue = (array3[index] && array3[index].length > 1) ? array3[index][1] : ""; 
                            displayText = `${idValue} - ${termValue}`;
                        } 
                        else if (type === 'rxterms') {
                            termValue = item1; // e.g., Aspirin (Oral Pill)
                            idValue = (array2['RXCUIS'] && array2['RXCUIS'][index]) ? array2['RXCUIS'][index][0] : "";
                            displayText = `${termValue} (RxCUI: ${idValue || 'N/A'})`;
                        }

                        const div = document.createElement('div');
                        div.className = 'autocomplete-item'; div.textContent = displayText;
                        div.onclick = function() {
                            inputElement.value = termValue; 
                            idElement.value = idValue;
                            suggestionBox.style.display = 'none';
                        };
                        suggestionBox.appendChild(div);
                    });
                } else { suggestionBox.style.display = 'none'; }
            } catch (err) { console.error("NLM API Error:", err); }
        }, 600); 
    });
}

function addComplaint() {
    const div = document.createElement('div'); div.className = 'form-row complaint-row';
    div.innerHTML = `
        <input type="text" name="hpo_term" class="hpo-term-search" placeholder="Search HPO Term (e.g. Nausea)" required>
        <input type="text" name="hpo_id" class="hpo-id-result" placeholder="HPO ID" readonly required style="background:#e9ecef; width: 100px; flex: none;">
        <input type="text" name="duration" placeholder="Duration (e.g. 3 days)" required>
        <button type="button" class="btn-small" onclick="this.parentElement.remove()" style="background:#e74c3c;">X</button>
    `;
    document.getElementById('complaintsList').appendChild(div);
    setupAutocomplete(div.querySelector('.hpo-term-search'), div.querySelector('.hpo-id-result'), 'hpo');
}

function addDiagnosis() {
    const div = document.createElement('div'); div.className = 'form-row diag-row';
    div.innerHTML = `
        <input type="text" name="icd10_term" class="icd10-term-search" placeholder="Search ICD-10 Code or Term" required>
        <input type="text" name="icd10_code" class="icd10-code-result" placeholder="ICD-10 Code" readonly required style="background:#e9ecef; width: 100px; flex: none;">
        <button type="button" class="btn-small" onclick="this.parentElement.remove()" style="background:#e74c3c;">X</button>
    `;
    document.getElementById('diagnosesList').appendChild(div);
    setupAutocomplete(div.querySelector('.icd10-term-search'), div.querySelector('.icd10-code-result'), 'icd10');
}

function addMedication() {
    medCount++; const div = document.createElement('div');
    div.className = 'med-box med-row'; div.id = `med_${medCount}`;
    div.innerHTML = `
        <div class="form-row">
            <input type="text" name="drug_name" class="drug-name-search" placeholder="Search Drug Name" required>
            <input type="text" name="rxcui" class="rxcui-result" placeholder="RxCUI" readonly required style="background:#e9ecef; width: 100px; flex: none;">
            <input type="text" name="dose" placeholder="Dose (e.g. 500mg)" required>
        </div>
        <div class="form-row">
            <input type="date" name="start_date" required title="Start Date">
            <input type="date" name="end_date" required title="End Date">
            <button type="button" class="btn-small" onclick="document.getElementById('med_${medCount}').remove()" style="background:#e74c3c;">Remove</button>
        </div>
        <div class="timings-list" id="timings_${medCount}">
            <strong>Dosage Timings: </strong>
            <button type="button" class="btn-small" onclick="addTiming(${medCount})">+ Add Time</button>
        </div>
    `;
    document.getElementById('medicationsList').appendChild(div);
    setupAutocomplete(div.querySelector('.drug-name-search'), div.querySelector('.rxcui-result'), 'rxterms');
    addTiming(medCount);
}

function addTiming(medId) {
    const timeDiv = document.createElement('span');
    timeDiv.innerHTML = `
        <input type="time" name="timing_${medId}" required style="margin: 5px;">
        <button type="button" onclick="this.parentElement.remove()" style="color:red; cursor:pointer; border:none; background:none;">✖</button>
    `;
    document.getElementById(`timings_${medId}`).appendChild(timeDiv);
}

function startPolling(uhid) {
    if (consentPollInterval) clearInterval(consentPollInterval);
    consentPollInterval = setInterval(async () => {
        try {
            // Added cache busting query parameter 't'
            const response = await fetch(`/api/consent_status/${uhid}?t=${new Date().getTime()}`);
            const data = await response.json();

            if (data.status === 'Accepted') {
                clearInterval(consentPollInterval);
                document.getElementById('statusPending').classList.add('hidden');
                document.getElementById('statusError').classList.add('hidden');
                document.getElementById('statusSuccess').classList.remove('hidden');
                document.getElementById('clinicalForm').classList.remove('hidden');

                if(document.querySelectorAll('.complaint-row').length === 0) {
                    addComplaint(); addDiagnosis(); addMedication();
                }
            } else if (data.status === 'Denied') {
                clearInterval(consentPollInterval);
                document.getElementById('statusPending').classList.add('hidden');
                document.getElementById('statusSuccess').classList.add('hidden');
                document.getElementById('statusError').classList.remove('hidden');
                document.getElementById('clinicalForm').classList.add('hidden');
            }
        } catch (error) { console.error("Polling error:", error); }
    }, 1500); 
}

async function resendConsent() {
    const uhid = document.getElementById('uhid').value;
    try {
        const response = await fetch(`/api/resend_consent/${uhid}`, { method: 'POST' });
        if (response.ok) {
            document.getElementById('statusError').classList.add('hidden');
            document.getElementById('statusPending').classList.remove('hidden');
            startPolling(uhid);
        } else {
            alert('Failed to resend consent. Has the patient scanned the QR code yet?');
        }
    } catch (e) { alert('Network Error'); }
}

document.getElementById('demographicsForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    const uhid = document.getElementById('uhid').value;
    const data = {
        uhid: uhid,
        name: document.getElementById('name').value,
        age: parseInt(document.getElementById('age').value),
        gender: document.getElementById('gender').value
    };

    try {
        const response = await fetch('/api/register', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data)
        });
        const result = await response.json();

        if (response.ok) {
            document.getElementById('btn-register').disabled = true;
            document.getElementById('linkingSection').classList.remove('hidden');
            document.getElementById('statusPending').classList.remove('hidden');

            const encodedLink = encodeURIComponent(result.telegram_link);
            document.getElementById('qrCodeImg').src = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodedLink}`;

            startPolling(uhid);
        } else { alert('Error: ' + result.message); }
    } catch (error) { alert('Network Error: ' + error.message); }
});

document.getElementById('clinicalForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    const data = { uhid: document.getElementById('uhid').value, complaints: [], diagnoses: [], medications: [] };

    document.querySelectorAll('.complaint-row').forEach(row => {
        data.complaints.push({
            hpo_id: row.querySelector('[name="hpo_id"]').value,
            hpo_term: row.querySelector('[name="hpo_term"]').value,
            duration: row.querySelector('[name="duration"]').value
        });
    });

    document.querySelectorAll('.diag-row').forEach(row => {
        data.diagnoses.push({
            icd10_code: row.querySelector('[name="icd10_code"]').value,
            icd10_term: row.querySelector('[name="icd10_term"]').value
        });
    });

    document.querySelectorAll('.med-row').forEach(row => {
        const medId = row.id.split('_')[1];
        const timings = [];
        row.querySelectorAll(`[name="timing_${medId}"]`).forEach(tInput => { timings.push(tInput.value); });
        data.medications.push({
            rxcui: row.querySelector('[name="rxcui"]').value,
            drug_name: row.querySelector('[name="drug_name"]').value,
            dose: row.querySelector('[name="dose"]').value,
            start_date: row.querySelector('[name="start_date"]').value,
            end_date: row.querySelector('[name="end_date"]').value,
            timings: timings
        });
    });

    try {
        const response = await fetch('/api/clinical', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data)
        });
        const result = await response.json();

        if (response.ok) {
            alert('Clinical Data Saved Successfully!');
            location.reload(); 
        } else { alert('Error: ' + result.message); }
    } catch (error) { alert('Network Error: ' + error.message); }
});
