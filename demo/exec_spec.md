# SaaS Analytics Dashboard — Dynamic Spec

## Description
A modern dark-themed analytics dashboard that loads metrics from an API
and displays them in stat cards with charts and activity feed.

## Assertions

### Structure
- The page has a sidebar with navigation links (Dashboard, Reports, Users, Settings)
- The main content area contains stat cards with values displayed
- There is a "Refresh Data" button
- An activity list exists showing recent events

### DOM: `document.title` == `Analytics Dashboard — Acme Corp`
The page title should match the expected project name.

### DOM: `document.querySelectorAll('.stat-card').length` >= `4`
At least 4 stat cards must exist (Revenue, Users, Conversion, Bounce Rate).

### DOM: `document.querySelector('.stat-card .value')` != `null`
Each stat card should have a value element.

### DOM: `document.querySelector('.sidebar nav a.active')` != `null`
There should be an active navigation item in the sidebar.

### JS: `typeof window.initDashboard` == `function`
The initDashboard function must be defined.

### JS: `typeof window.loadMetrics` == `function`
The loadMetrics async function must be defined.

### JS: `typeof window.updateCards` == `function`
The updateCards function must be defined.

### JS: `typeof window.refreshData` == `function`
The refreshData function must be defined.

### Console: no errors
No console.error() calls should fire during page load.

### Console: no warnings
At most 3 console.warn() calls are allowed during page load.

### Behavior: refreshData disables button
Calling refreshData() should set the refresh button to disabled.

### Behavior: refreshData shows loading text
After calling refreshData(), the button text should show "Refreshing...".

### Style: `.sidebar` `display` == `flex`
The sidebar should be a flex container.

### Style: `.stats-grid` `display` == `grid`
Stat cards should be laid out in a grid.

### Async: page loads without uncaught errors
The page must load with no unhandled promise rejections or runtime errors.

### Timeout: 5000ms
Each individual assertion must complete within 5 seconds.

## Exemptions
- Refresh button eventually returns to "Refresh Data" after loadMetrics resolves
- console.warn for "Could not load live data" is acceptable (API unavailable)
