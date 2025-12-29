let config = { profiles: {} };
let currentProfile = null;
const days = [
	"Sunday",
	"Monday",
	"Tuesday",
	"Wednesday",
	"Thursday",
	"Friday",
	"Saturday"
];

async function loadConfig() {
	const response = await fetch("/api/config");
	config = await response.json();

	// Ensure config has profiles structure
	if (!config.profiles) {
		config.profiles = {};
	}

	// Find active profile or use first one
	currentProfile = null;
	for (const [name, data] of Object.entries(config.profiles)) {
		if (data.isActive) {
			currentProfile = name;
			break;
		}
	}

	if (!currentProfile && Object.keys(config.profiles).length > 0) {
		currentProfile = Object.keys(config.profiles)[0];
		config.profiles[currentProfile].isActive = true;
	}

	updateProfileSelector();
	renderSchedule();
}

function updateProfileSelector() {
	const select = document.getElementById("profileSelect");
	select.innerHTML = "";

	for (const profileName of Object.keys(config.profiles)) {
		const option = document.createElement("option");
		option.value = profileName;
		option.textContent = profileName;
		option.selected = profileName === currentProfile;
		select.appendChild(option);
	}

	// Update copy from profile options
	const copySelect = document.getElementById("copyFromProfile");
	copySelect.innerHTML = '<option value="">Default schedule</option>';
	for (const profileName of Object.keys(config.profiles)) {
		const option = document.createElement("option");
		option.value = profileName;
		option.textContent = profileName;
		copySelect.appendChild(option);
	}
}

function switchProfile() {
	const select = document.getElementById("profileSelect");
	const newProfile = select.value;

	if (newProfile !== currentProfile) {
		// Deactivate all profiles
		for (const name in config.profiles) {
			config.profiles[name].isActive = false;
		}

		// Activate selected profile
		config.profiles[newProfile].isActive = true;
		currentProfile = newProfile;

		renderSchedule();
		saveSchedule();
	}
}

function renderSchedule() {
	if (!currentProfile || !config.profiles[currentProfile]) {
		return;
	}

	const schedule = config.profiles[currentProfile].schedule;
	const tbody = document.getElementById("scheduleBody");
	tbody.innerHTML = "";

	for (let hour = 0; hour < 24; hour++) {
		const row = document.createElement("tr");

		const hourCell = document.createElement("td");
		hourCell.className = "hour-label";
		hourCell.textContent = `${hour.toString().padStart(2, "0")}:00`;
		row.appendChild(hourCell);

		days.forEach((day) => {
			const cell = document.createElement("td");
			const volume = schedule[day][hour.toString()];

			cell.innerHTML = `
                        <div class="volume-cell" onclick="editCell('${day}', ${hour})">
                            <div class="volume-bar" style="height: ${volume}%"></div>
                            <div class="volume-label">${volume}%</div>
                        </div>
                    `;

			row.appendChild(cell);
		});

		tbody.appendChild(row);
	}
}

function editCell(day, hour) {
	const schedule = config.profiles[currentProfile].schedule;
	const currentVolume = schedule[day][hour.toString()];
	const newVolume = prompt(
		`Set volume for ${day} at ${hour}:00\n(0-100)`,
		currentVolume
	);

	if (newVolume !== null) {
		const vol = Math.max(0, Math.min(100, parseInt(newVolume) || 0));
		schedule[day][hour.toString()] = vol;
		renderSchedule();
	}
}

async function saveSchedule() {
	try {
		const response = await fetch("/api/config", {
			method: "POST",
			headers: {
				"Content-Type": "application/json"
			},
			body: JSON.stringify(config)
		});

		if (response.ok) {
			showStatus("Schedule saved successfully! ✓");
		}
	} catch (error) {
		showStatus("Error saving schedule: " + error.message, true);
	}
}

function showStatus(message, isError = false) {
	const status = document.getElementById("status");
	status.textContent = message;
	status.classList.add("show");
	if (isError) {
		status.classList.add("error");
	} else {
		status.classList.remove("error");
	}
	setTimeout(() => status.classList.remove("show"), 3000);
}

function showNewProfile() {
	document.getElementById("newProfileModal").classList.add("active");
	document.getElementById("newProfileName").value = "";
}

function closeNewProfile() {
	document.getElementById("newProfileModal").classList.remove("active");
}

function createDefaultSchedule() {
	const schedule = {};
	days.forEach((day) => {
		schedule[day] = {};
		for (let hour = 0; hour < 24; hour++) {
			if (hour >= 22 || hour < 6) {
				schedule[day][hour.toString()] = 30;
			} else {
				schedule[day][hour.toString()] = 70;
			}
		}
	});
	return schedule;
}

function createNewProfile() {
	const name = document.getElementById("newProfileName").value.trim();
	const copyFrom = document.getElementById("copyFromProfile").value;

	if (!name) {
		showStatus("Please enter a profile name", true);
		return;
	}

	if (config.profiles[name]) {
		showStatus("Profile already exists", true);
		return;
	}

	let schedule;
	if (copyFrom && config.profiles[copyFrom]) {
		// Deep copy the schedule
		schedule = JSON.parse(
			JSON.stringify(config.profiles[copyFrom].schedule)
		);
	} else {
		schedule = createDefaultSchedule();
	}

	config.profiles[name] = {
		name: name,
		isActive: false,
		schedule: schedule
	};

	currentProfile = name;

	// Deactivate all other profiles
	for (const profileName in config.profiles) {
		config.profiles[profileName].isActive = false;
	}
	config.profiles[name].isActive = true;

	updateProfileSelector();
	renderSchedule();
	closeNewProfile();
	saveSchedule();
	showStatus(`Profile "${name}" created`);
}

function showRenameProfile() {
	if (!currentProfile) return;
	document.getElementById("renameProfileModal").classList.add("active");
	document.getElementById("renameProfileName").value = currentProfile;
}

function closeRenameProfile() {
	document.getElementById("renameProfileModal").classList.remove("active");
}

function applyRenameProfile() {
	const newName = document.getElementById("renameProfileName").value.trim();

	if (!newName) {
		showStatus("Please enter a profile name", true);
		return;
	}

	if (newName === currentProfile) {
		closeRenameProfile();
		return;
	}

	if (config.profiles[newName]) {
		showStatus("Profile name already exists", true);
		return;
	}

	const oldName = currentProfile;
	config.profiles[newName] = config.profiles[oldName];
	config.profiles[newName].name = newName;
	delete config.profiles[oldName];

	currentProfile = newName;

	updateProfileSelector();
	closeRenameProfile();
	saveSchedule();
	showStatus(`Profile renamed to "${newName}"`);
}

function deleteProfile() {
	if (!currentProfile) return;

	if (Object.keys(config.profiles).length === 1) {
		showStatus("Cannot delete the last profile", true);
		return;
	}

	if (!confirm(`Delete profile "${currentProfile}"?`)) {
		return;
	}

	const wasActive = config.profiles[currentProfile].isActive;
	delete config.profiles[currentProfile];

	// Switch to first available profile
	currentProfile = Object.keys(config.profiles)[0];
	if (wasActive) {
		config.profiles[currentProfile].isActive = true;
	}

	updateProfileSelector();
	renderSchedule();
	saveSchedule();
	showStatus("Profile deleted");
}

function showBulkEdit() {
	document.getElementById("bulkEditModal").classList.add("active");
}

function closeBulkEdit() {
	document.getElementById("bulkEditModal").classList.remove("active");
}

function applyBulkEdit() {
	const day = document.getElementById("bulkDay").value;
	const volume = parseInt(document.getElementById("bulkVolume").value);
	const schedule = config.profiles[currentProfile].schedule;

	for (let hour = 0; hour < 24; hour++) {
		schedule[day][hour.toString()] = volume;
	}

	renderSchedule();
	closeBulkEdit();
	showStatus(`Set all hours for ${day} to ${volume}%`);
}

function copyDay() {
	document.getElementById("copyDayModal").classList.add("active");
}

function closeCopyDay() {
	document.getElementById("copyDayModal").classList.remove("active");
}

function applyCopyDay() {
	const fromDay = document.getElementById("copyFrom").value;
	const toDay = document.getElementById("copyTo").value;
	const schedule = config.profiles[currentProfile].schedule;

	schedule[toDay] = { ...schedule[fromDay] };
	renderSchedule();
	closeCopyDay();
	showStatus(`Copied schedule from ${fromDay} to ${toDay}`);
}

function resetSchedule() {
	if (
		confirm(
			"Reset schedule to defaults? This will set 30% volume for night hours (22:00-06:00) and 70% for day hours."
		)
	) {
		const schedule = config.profiles[currentProfile].schedule;
		days.forEach((day) => {
			for (let hour = 0; hour < 24; hour++) {
				if (hour >= 22 || hour < 6) {
					schedule[day][hour.toString()] = 30;
				} else {
					schedule[day][hour.toString()] = 70;
				}
			}
		});
		renderSchedule();
		showStatus("Schedule reset to defaults");
	}
}

// Load config on page load
loadConfig();
