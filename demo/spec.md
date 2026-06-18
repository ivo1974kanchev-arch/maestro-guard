# SaaS Analytics Dashboard

## Overview
Build a modern dark-themed analytics dashboard for monitoring SaaS metrics.

## Layout
- Left sidebar with navigation: Dashboard, Analytics, Settings, Users, Billing
- Top header bar with search and user profile
- Main content area with metric cards grid
- Charts section below metrics

## Required Elements
- Metric cards showing: Total Revenue, Active Users, Conversion Rate, Bounce Rate
- Line chart for revenue over time
- Bar chart for user growth
- Activity feed showing recent user actions
- Stats panel with key performance indicators

## Technical Requirements
- Responsive design (mobile, tablet, desktop)
- Dark theme with accent colors
- Interactive charts (use canvas or SVG)
- Real-time data simulation via JavaScript
- Loading states and error handling

## Color Scheme
- Background: dark (#0f1117)
- Cards: slightly lighter (#1a1d27)
- Accent: purple (#6c5ce7)
- Text: white and gray (#a0a0b0)

## JavaScript Behaviors
- Fetch and display metrics on page load
- Refresh data every 30 seconds
- Handle API errors gracefully (show cached data, log warnings)
- Responsive chart resizing on window resize
- Active state for sidebar navigation
