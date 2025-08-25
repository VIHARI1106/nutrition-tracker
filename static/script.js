const $ = (s) => document.querySelector(s);
const resultsEl = $("#results");
const logListEl = $("#logList");

const calTotalEl = $("#calTotal");
const proTotalEl = $("#proTotal");
const fatTotalEl = $("#fatTotal");
const carbTotalEl = $("#carbTotal");

let barChart, pieChart, trendChart, monthlyChart;
let currentDate = new Date().toISOString().split("T")[0];

document.addEventListener("DOMContentLoaded", init);

function init() {
  $("#datePicker").value = currentDate;
  $("#datePicker").addEventListener("change", (e) => {
    currentDate = e.target.value;
    refreshLogs();
  });
  $("#searchBtn").addEventListener("click", onSearch);
  $("#searchInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") onSearch();
  });
  $("#exportBtn").addEventListener("click", () => {
    window.location.href = "/api/logs/export";
  });
  refreshLogs();
  refreshTrends();
  refreshMonthly();
}

async function onSearch() {
  const q = $("#searchInput").value.trim();
  if (!q) return;
  resultsEl.innerHTML = "Searching...";
  const res = await fetch(`/api/search?q=${encodeURIComponent(q)}&enrich=1&limit=6`);
  const data = await res.json();
  renderResults(data.results || []);
}

function renderResults(items) {
  resultsEl.innerHTML = "";
  if (items.length === 0) {
      resultsEl.innerHTML = "No results found.";
      return;
  }
  items.forEach((it) => {
    const row = document.createElement("div");
    row.className = "result-item";
    row.innerHTML = `
      <div><b>${it.name}</b></div>
      <small>kcal: ${Math.round(it.calories)}</small>
      <small>P: ${Math.round(it.protein)}g</small>
      <small>F: ${Math.round(it.fat)}g</small>
      <small>C: ${Math.round(it.carbs)}g</small>
      <button class="add-btn">Add</button>
    `;
    row.querySelector("button").onclick = async () => {
      const qty = parseFloat(prompt("Quantity?", "1")) || 1;
      await fetch("/api/log", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({
          name: it.name,
          quantity: qty,
          calories: it.calories,
          protein: it.protein,
          fat: it.fat,
          carbs: it.carbs,
          log_date: currentDate
        })
      });
      refreshLogs();
      refreshTrends();
      refreshMonthly();
    };
    resultsEl.appendChild(row);
  });
}

async function refreshLogs() {
  const res = await fetch(`/api/logs/by-date?date=${currentDate}`);
  const data = await res.json();
  renderLogList(data.entries);
  renderTotals(data.totals);
}

function renderLogList(entries) {
  logListEl.innerHTML = "";
  if (entries.length === 0) {
      logListEl.innerHTML = "No logs for this date.";
      return;
  }
  entries.forEach((e) => {
    const row = document.createElement("div");
    row.className = "log-item";
    row.innerHTML = `
      <div><b>${e.name}</b><br/><small>${e.quantity} serving(s)</small></div>
      <small>kcal ${Math.round(e.calories * e.quantity)}</small>
      <small>P ${Math.round(e.protein * e.quantity)}g</small>
      <small>F ${Math.round(e.fat * e.quantity)}g</small>
      <small>C ${Math.round(e.carbs * e.quantity)}g</small>
      <button class="del-btn">❌</button>
    `;
    row.querySelector("button").onclick = async () => {
      await fetch(`/api/logs/${e.id}`, {method:"DELETE"});
      refreshLogs();
      refreshTrends();
      refreshMonthly();
    };
    logListEl.appendChild(row);
  });
}

function renderTotals(t) {
  // Update total value displays
  calTotalEl.textContent = Math.round(t.calories);
  proTotalEl.textContent = Math.round(t.protein);
  fatTotalEl.textContent = Math.round(t.fat);
  carbTotalEl.textContent = Math.round(t.carbs);

  // Bar Chart (Calories + Macros)
  const barData = {
    labels: ["Calories", "Protein", "Fat", "Carbs"],
    datasets: [{
      label: 'Daily Intake',
      data: [t.calories, t.protein, t.fat, t.carbs],
      backgroundColor: ["#4ade80", "#60a5fa", "#f87171", "#facc15"],
      borderWidth: 1
    }]
  };
  const barOptions = {
    responsive: true,
    plugins: {
      legend: { display: false },
      title: { display: false }
    },
    scales: {
        y: { beginAtZero: true }
    }
  };
  if (barChart) {
    barChart.data = barData;
    barChart.update();
  } else {
    barChart = new Chart($("#dailyBarChart"), { type: "bar", data: barData, options: barOptions });
  }

  // Pie Chart (Macros only)
  const pieData = {
    labels: ["Protein", "Fat", "Carbs"],
    datasets: [{
      data: [t.protein, t.fat, t.carbs],
      backgroundColor: ["#60a5fa", "#f87171", "#facc15"]
    }]
  };
  const pieOptions = {
    responsive: true,
    plugins: {
      legend: {
        position: 'bottom'
      }
    }
  };
  if (pieChart) {
    pieChart.data = pieData;
    pieChart.update();
  } else {
    pieChart = new Chart($("#dailyPieChart"), { type: "pie", data: pieData, options: pieOptions });
  }

  // Progress Bars (assuming goals are set)
  const goals = {
    calories: 2000,
    protein: 150,
    fat: 65,
    carbs: 250
  };
  
  $("#cal-current").textContent = Math.round(t.calories);
  $("#pro-current").textContent = Math.round(t.protein);
  $("#fat-current").textContent = Math.round(t.fat);
  $("#carb-current").textContent = Math.round(t.carbs);

  $("#cal-bar").style.width = `${Math.min((t.calories / goals.calories) * 100, 100)}%`;
  $("#pro-bar").style.width = `${Math.min((t.protein / goals.protein) * 100, 100)}%`;
  $("#fat-bar").style.width = `${Math.min((t.fat / goals.fat) * 100, 100)}%`;
  $("#carb-bar").style.width = `${Math.min((t.carbs / goals.carbs) * 100, 100)}%`;
}

async function refreshTrends() {
  const res = await fetch("/api/logs/aggregate?mode=week");
  const data = await res.json();
  const chartData = {
    labels: data.map(d=>d.log_date),
    datasets:[{label:"Calories", data:data.map(d=>d.t_calories), borderColor:"#4ade80", fill:false}]
  };
  const options = { responsive: true, plugins: { legend: { display: true } } };
  if(trendChart){trendChart.data=chartData;trendChart.update();}
  else {trendChart=new Chart($("#trendChart"),{type:"line",data:chartData, options: options});}
}

async function refreshMonthly() {
  const res = await fetch("/api/logs/aggregate?mode=month");
  const data = await res.json();
  const chartData = {
    labels: data.map(d=>d.log_date),
    datasets:[{label:"Monthly Calories", data:data.map(d=>d.t_calories), backgroundColor:"#60a5fa"}]
  };
  const options = { responsive: true, plugins: { legend: { display: true } } };
  if(monthlyChart){monthlyChart.data=chartData;monthlyChart.update();}
  else {monthlyChart=new Chart($("#monthlyChart"),{type:"bar",data:chartData, options: options});}
}