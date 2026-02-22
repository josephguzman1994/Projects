#!/usr/bin/env python3
"""
Retirement Savings Goal Calculator

This script calculates the target portfolio balance needed for retirement,
accounting for inflation and assuming a 3% withdrawal rate.

For inheritance-house scenarios (keep vs. sell and invest), see
inheritance_house_scenarios.py in this directory.
"""

import json
import csv
from datetime import datetime

try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Note: matplotlib not available. Visualization will be skipped.")


def calculate_retirement_goal(
    desired_annual_income: float,
    inflation_rate: float,
    years_until_retirement: int,
    withdrawal_rate: float = 0.03,
    social_security_annual: float = 0.0
) -> dict:
    """
    Calculate the retirement savings goal.
    
    Args:
        desired_annual_income: Desired annual income in today's dollars
        inflation_rate: Annual inflation rate (e.g., 0.03 for 3%)
        years_until_retirement: Number of years until retirement
        withdrawal_rate: Annual withdrawal rate as percentage of portfolio (default 3%)
        social_security_annual: Estimated annual Social Security benefit in today's dollars
    
    Returns:
        Dictionary containing calculation results
    """
    # Calculate inflation-adjusted income at retirement
    future_annual_income = desired_annual_income * ((1 + inflation_rate) ** years_until_retirement)
    
    # Calculate inflation-adjusted Social Security at retirement
    future_social_security = social_security_annual * ((1 + inflation_rate) ** years_until_retirement)
    
    # Calculate income gap that needs to be covered by portfolio
    income_gap = future_annual_income - future_social_security
    
    # Calculate required portfolio balance (income gap / withdrawal_rate)
    # If Social Security covers everything, portfolio needed is 0
    required_portfolio_balance = max(0, income_gap / withdrawal_rate)
    
    return {
        'desired_income_today': desired_annual_income,
        'social_security_today': social_security_annual,
        'inflation_rate': inflation_rate,
        'years_until_retirement': years_until_retirement,
        'withdrawal_rate': withdrawal_rate,
        'future_annual_income': future_annual_income,
        'future_social_security': future_social_security,
        'income_gap': income_gap,
        'required_portfolio_balance': required_portfolio_balance
    }


def calculate_roth_ira_growth(
    current_balance: float,
    annual_contribution: float,
    annual_return_rate: float,
    years: int
) -> dict:
    """
    Calculate projected Roth IRA balance with regular contributions and compound growth.
    
    Args:
        current_balance: Current balance in the Roth IRA
        annual_contribution: Amount contributed each year
        annual_return_rate: Expected annual return rate (e.g., 0.07 for 7%)
        years: Number of years until retirement
    
    Returns:
        Dictionary containing calculation results
    """
    # Future value of current balance (compound growth)
    future_value_current = current_balance * ((1 + annual_return_rate) ** years)
    
    # Future value of annual contributions (annuity formula)
    # Formula: PMT * [((1 + r)^n - 1) / r]
    if annual_return_rate > 0:
        future_value_contributions = annual_contribution * (((1 + annual_return_rate) ** years - 1) / annual_return_rate)
    else:
        # If return rate is 0, just multiply contributions by years
        future_value_contributions = annual_contribution * years
    
    # Total projected balance
    total_projected_balance = future_value_current + future_value_contributions
    
    # Calculate total contributions made
    total_contributions = current_balance + (annual_contribution * years)
    
    # Calculate total growth (earnings)
    total_growth = total_projected_balance - total_contributions
    
    return {
        'current_balance': current_balance,
        'annual_contribution': annual_contribution,
        'annual_return_rate': annual_return_rate,
        'years': years,
        'future_value_current': future_value_current,
        'future_value_contributions': future_value_contributions,
        'total_projected_balance': total_projected_balance,
        'total_contributions': total_contributions,
        'total_growth': total_growth
    }


def calculate_inheritance_projection(
    mother_portfolio_value: float,
    growth_rate: float,
    years_until_inheritance: int,
    years_until_retirement: int,
    number_of_beneficiaries: int = 3
) -> dict:
    """
    Calculate projected inheritance value at retirement.
    
    Args:
        mother_portfolio_value: Current value of mother's portfolio
        growth_rate: Assumed annual growth rate for the portfolio
        years_until_inheritance: Years until inheritance is received
        years_until_retirement: Years until retirement
        number_of_beneficiaries: Number of people splitting inheritance (default 3)
    
    Returns:
        Dictionary containing calculation results
    """
    # Calculate your share (equal split)
    your_share = mother_portfolio_value / number_of_beneficiaries
    
    # If inheritance comes before retirement, grow until inheritance, then flat
    if years_until_inheritance < years_until_retirement:
        # Grow until inheritance is received
        value_at_inheritance = your_share * ((1 + growth_rate) ** years_until_inheritance)
        # Then leave flat until retirement (no growth)
        value_at_retirement = value_at_inheritance
        years_growing = years_until_inheritance
        years_flat = years_until_retirement - years_until_inheritance
    else:
        # If inheritance comes at or after retirement, just grow until retirement
        value_at_retirement = your_share * ((1 + growth_rate) ** years_until_retirement)
        value_at_inheritance = value_at_retirement
        years_growing = years_until_retirement
        years_flat = 0
    
    # Calculate total growth
    total_growth = value_at_retirement - your_share
    
    return {
        'mother_portfolio_value': mother_portfolio_value,
        'your_share_today': your_share,
        'growth_rate': growth_rate,
        'years_until_inheritance': years_until_inheritance,
        'years_until_retirement': years_until_retirement,
        'value_at_inheritance': value_at_inheritance,
        'value_at_retirement': value_at_retirement,
        'years_growing': years_growing,
        'years_flat': years_flat,
        'total_growth': total_growth,
        'number_of_beneficiaries': number_of_beneficiaries
    }


def format_currency(amount: float) -> str:
    """Format a number as currency."""
    return f"${amount:,.2f}"


def print_retirement_goal(results: dict):
    """Print retirement goal calculation results in a readable format."""
    print("\n" + "="*60)
    print("RETIREMENT SAVINGS GOAL CALCULATION")
    print("="*60)
    print(f"\nInput Parameters:")
    print(f"  Desired Annual Income (today's dollars): {format_currency(results['desired_income_today'])}")
    if results.get('social_security_today', 0) > 0:
        print(f"  Social Security (today's dollars): {format_currency(results['social_security_today'])}")
    print(f"  Assumed Inflation Rate: {results['inflation_rate']*100:.2f}%")
    print(f"  Years Until Retirement: {results['years_until_retirement']}")
    print(f"  Withdrawal Rate: {results['withdrawal_rate']*100:.1f}%")
    
    print(f"\nResults:")
    print(f"  Inflation-Adjusted Income at Retirement: {format_currency(results['future_annual_income'])}")
    if results.get('future_social_security', 0) > 0:
        print(f"  Social Security at Retirement: {format_currency(results['future_social_security'])}")
        print(f"    (Note: Social Security benefits receive annual COLA adjustments)")
        print(f"    (This projection assumes COLA matches the assumed inflation rate)")
        print(f"  Income Gap (portfolio must cover): {format_currency(results['income_gap'])}")
    print(f"  Required Portfolio Balance: {format_currency(results['required_portfolio_balance'])}")
    print("\n" + "="*60)
    print("\nNote: This calculation assumes:")
    print("  - A constant inflation rate over the period")
    print("  - Social Security benefits receive annual COLA (Cost-of-Living Adjustment)")
    print("    based on CPI-W, which typically tracks general inflation")
    print("  - The withdrawal rate represents a sustainable annual income")
    print("  - The portfolio balance remains stable (4% rule typically assumes")
    print("    portfolio growth offsets withdrawals over 30+ years)")
    print("="*60 + "\n")


def print_roth_ira_results(roth_results: dict, retirement_goal: float = None):
    """Print Roth IRA growth projection results."""
    print("\n" + "="*60)
    print("ROTH IRA GROWTH PROJECTION")
    print("="*60)
    print(f"\nInput Parameters:")
    print(f"  Current Balance: {format_currency(roth_results['current_balance'])}")
    print(f"  Annual Contribution: {format_currency(roth_results['annual_contribution'])}")
    print(f"  Assumed Annual Return: {roth_results['annual_return_rate']*100:.2f}%")
    print(f"  Years Until Retirement: {roth_results['years']}")
    
    print(f"\nProjection Breakdown:")
    print(f"  Growth on Current Balance: {format_currency(roth_results['future_value_current'])}")
    print(f"  Growth on Future Contributions: {format_currency(roth_results['future_value_contributions'])}")
    print(f"  Total Projected Balance: {format_currency(roth_results['total_projected_balance'])}")
    
    print(f"\nContribution Summary:")
    print(f"  Total Contributions Made: {format_currency(roth_results['total_contributions'])}")
    print(f"  Total Investment Growth: {format_currency(roth_results['total_growth'])}")
    print(f"  Growth as % of Total: {(roth_results['total_growth'] / roth_results['total_projected_balance'] * 100):.1f}%")
    
    if retirement_goal:
        shortfall = retirement_goal - roth_results['total_projected_balance']
        coverage = (roth_results['total_projected_balance'] / retirement_goal) * 100
        print(f"\nComparison to Retirement Goal:")
        print(f"  Retirement Goal: {format_currency(retirement_goal)}")
        print(f"  Roth IRA Projection: {format_currency(roth_results['total_projected_balance'])}")
        if shortfall > 0:
            print(f"  Shortfall: {format_currency(shortfall)}")
            print(f"  Coverage: {coverage:.1f}% of goal")
        else:
            print(f"  Surplus: {format_currency(-shortfall)}")
            print(f"  Coverage: {coverage:.1f}% of goal")
    
    print("="*60 + "\n")


def print_inheritance_results(inheritance_results: dict, retirement_goal: float = None):
    """Print inheritance projection results."""
    print("\n" + "="*60)
    print("INHERITANCE PROJECTION")
    print("="*60)
    print(f"\nInput Parameters:")
    print(f"  Mother's Portfolio Value (today): {format_currency(inheritance_results['mother_portfolio_value'])}")
    print(f"  Number of Beneficiaries: {inheritance_results['number_of_beneficiaries']}")
    print(f"  Your Share (today): {format_currency(inheritance_results['your_share_today'])}")
    print(f"  Assumed Growth Rate: {inheritance_results['growth_rate']*100:.2f}%")
    print(f"  Years Until Inheritance: {inheritance_results['years_until_inheritance']}")
    print(f"  Years Until Retirement: {inheritance_results['years_until_retirement']}")
    
    print(f"\nProjection:")
    if inheritance_results['years_until_inheritance'] < inheritance_results['years_until_retirement']:
        print(f"  Value at Inheritance: {format_currency(inheritance_results['value_at_inheritance'])}")
        print(f"    (Grows for {inheritance_results['years_growing']} years)")
        print(f"  Value at Retirement: {format_currency(inheritance_results['value_at_retirement'])}")
        print(f"    (Flat for {inheritance_results['years_flat']} years after inheritance)")
        print(f"  Note: Assumes inheritance is not reinvested after receipt")
    else:
        print(f"  Value at Retirement: {format_currency(inheritance_results['value_at_retirement'])}")
        print(f"    (Grows for {inheritance_results['years_growing']} years)")
    
    print(f"\nGrowth Summary:")
    print(f"  Total Growth: {format_currency(inheritance_results['total_growth'])}")
    print(f"  Growth as % of Initial Share: {(inheritance_results['total_growth'] / inheritance_results['your_share_today'] * 100):.1f}%")
    
    if retirement_goal:
        shortfall = retirement_goal - inheritance_results['value_at_retirement']
        coverage = (inheritance_results['value_at_retirement'] / retirement_goal) * 100
        print(f"\nComparison to Retirement Goal:")
        print(f"  Retirement Goal: {format_currency(retirement_goal)}")
        print(f"  Inheritance Projection: {format_currency(inheritance_results['value_at_retirement'])}")
        if shortfall > 0:
            print(f"  Shortfall: {format_currency(shortfall)}")
            print(f"  Coverage: {coverage:.1f}% of goal")
        else:
            print(f"  Surplus: {format_currency(-shortfall)}")
            print(f"  Coverage: {coverage:.1f}% of goal")
    
    print("="*60 + "\n")


def print_total_assets_summary(
    retirement_goal: float,
    withdrawal_rate: float,
    inflation_rate: float,
    years_until_retirement: int,
    roth_balance: float = None,
    inheritance_value: float = None
):
    """Print summary of all assets compared to retirement goal."""
    print("\n" + "="*60)
    print("TOTAL ASSETS SUMMARY")
    print("="*60)
    
    total_assets = 0
    print(f"\nRetirement Goal: {format_currency(retirement_goal)}")
    print(f"\nProjected Assets at Retirement:")
    
    if roth_balance is not None:
        print(f"  Roth IRA: {format_currency(roth_balance)}")
        total_assets += roth_balance
    
    if inheritance_value is not None:
        print(f"  Inheritance: {format_currency(inheritance_value)}")
        total_assets += inheritance_value
    
    if roth_balance is None and inheritance_value is None:
        print("  (No assets modeled)")
    else:
        print(f"\n  Total Projected Assets: {format_currency(total_assets)}")
        
        # Calculate annual income that can be generated from total assets (in future dollars)
        projected_annual_income_future = total_assets * withdrawal_rate
        
        # Convert back to today's dollars for comparison
        # Formula: Future Value / (1 + inflation_rate)^years
        projected_annual_income_today = projected_annual_income_future / ((1 + inflation_rate) ** years_until_retirement)
        
        print(f"\nProjected Annual Income:")
        print(f"  At retirement (future dollars): {format_currency(projected_annual_income_future)}")
        print(f"  In today's dollars (purchasing power): {format_currency(projected_annual_income_today)}")
        print(f"  (Based on {withdrawal_rate*100:.1f}% withdrawal rate)")
        print(f"  Note: The 'today's dollars' amount shows what this income")
        print(f"        would feel like if you received it today.")
        
        shortfall = retirement_goal - total_assets
        coverage = (total_assets / retirement_goal) * 100
        
        print(f"\nOverall Comparison:")
        if shortfall > 0:
            print(f"  Shortfall: {format_currency(shortfall)}")
            print(f"  Coverage: {coverage:.1f}% of goal")
            print(f"  Additional Needed: {format_currency(shortfall)}")
        else:
            print(f"  Surplus: {format_currency(-shortfall)}")
            print(f"  Coverage: {coverage:.1f}% of goal")
            print(f"  You exceed your goal by: {format_currency(-shortfall)}")
    
    print("="*60 + "\n")


def calculate_roth_ira_trajectory(
    current_balance: float,
    annual_contribution: float,
    annual_return_rate: float,
    years: int
) -> tuple:
    """
    Calculate Roth IRA balance at each year.
    
    Returns:
        Tuple of (years_list, balance_list)
    """
    years_list = list(range(years + 1))
    balance_list = []
    
    balance = current_balance
    for year in years_list:
        if year == 0:
            balance_list.append(balance)
        else:
            # Add growth from previous year
            balance = balance * (1 + annual_return_rate)
            # Add annual contribution
            balance += annual_contribution
            balance_list.append(balance)
    
    return years_list, balance_list


def calculate_inheritance_trajectory(
    mother_portfolio_value: float,
    growth_rate: float,
    years_until_inheritance: int,
    years_until_retirement: int,
    number_of_beneficiaries: int = 3
) -> tuple:
    """
    Calculate inheritance value trajectory over time.
    
    Returns:
        Tuple of (years_list, value_list)
    """
    years_list = list(range(years_until_retirement + 1))
    value_list = []
    
    your_share = mother_portfolio_value / number_of_beneficiaries
    
    for year in years_list:
        if year <= years_until_inheritance:
            # Growing until inheritance
            value = your_share * ((1 + growth_rate) ** year)
        else:
            # Flat after inheritance
            value_at_inheritance = your_share * ((1 + growth_rate) ** years_until_inheritance)
            value = value_at_inheritance
        value_list.append(value)
    
    return years_list, value_list


def create_retirement_visualization(
    retirement_goal: float,
    years_until_retirement: int,
    inflation_rate: float,
    roth_trajectory: tuple = None,
    inheritance_trajectory: tuple = None
):
    """
    Create a visualization of retirement planning.
    
    Args:
        retirement_goal: Target portfolio balance at retirement (in future dollars)
        years_until_retirement: Years until retirement
        inflation_rate: Annual inflation rate
        roth_trajectory: Tuple of (years_list, balance_list) for Roth IRA
        inheritance_trajectory: Tuple of (years_list, value_list) for inheritance
    """
    if not MATPLOTLIB_AVAILABLE:
        print("\nVisualization skipped: matplotlib not available.")
        print("Install with: pip install matplotlib numpy")
        return
    
    fig, ax = plt.subplots(figsize=(12, 8))
    
    # Create time axis
    years_list = list(range(years_until_retirement + 1))
    
    # Plot retirement goal (grows with inflation)
    goal_line = []
    for year in years_list:
        # Goal at retirement is the target, work backwards
        # Goal today = goal_at_retirement / (1 + inflation)^years_until_retirement
        goal_today = retirement_goal / ((1 + inflation_rate) ** years_until_retirement)
        # Goal at this year = goal_today * (1 + inflation)^year
        goal_at_year = goal_today * ((1 + inflation_rate) ** year)
        goal_line.append(goal_at_year)
    
    ax.plot(years_list, goal_line, 'r--', linewidth=2, 
            label=f'Retirement Goal (grows with inflation)', alpha=0.7)
    
    # Plot Roth IRA trajectory
    if roth_trajectory:
        roth_years, roth_balances = roth_trajectory
        ax.plot(roth_years, roth_balances, 'b-', linewidth=2, label='Roth IRA', marker='o', markersize=3)
    
    # Plot inheritance trajectory
    if inheritance_trajectory:
        inh_years, inh_values = inheritance_trajectory
        ax.plot(inh_years, inh_values, 'g-', linewidth=2, label='Inheritance', marker='s', markersize=3)
    
    # Calculate and plot total assets if both are available
    total_assets = None
    if roth_trajectory and inheritance_trajectory:
        roth_years, roth_balances = roth_trajectory
        inh_years, inh_values = inheritance_trajectory
        
        # Align the trajectories (they should have same length, but be safe)
        min_len = min(len(roth_balances), len(inh_values))
        total_assets = [roth_balances[i] + inh_values[i] for i in range(min_len)]
        total_years = roth_years[:min_len]
        
        ax.plot(total_years, total_assets, 'purple', linewidth=3, label='Total Assets', marker='D', markersize=4)
    
    # Formatting
    ax.set_xlabel('Years Until Retirement', fontsize=12, fontweight='bold')
    ax.set_ylabel('Portfolio Value ($)', fontsize=12, fontweight='bold')
    ax.set_title('Retirement Planning Projection', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.legend(loc='best', fontsize=10)
    
    # Format y-axis to show currency in millions/thousands
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x/1e6:.1f}M' if x >= 1e6 else f'${x/1e3:.0f}K'))
    
    # Add annotation at retirement point
    if roth_trajectory or inheritance_trajectory:
        if total_assets is not None:
            final_value = total_assets[-1]
        elif roth_trajectory:
            _, roth_balances = roth_trajectory
            final_value = roth_balances[-1]
        else:
            _, inh_values = inheritance_trajectory
            final_value = inh_values[-1]
        
        ax.annotate(f'Retirement\n${final_value:,.0f}',
                   xy=(years_until_retirement, final_value),
                   xytext=(years_until_retirement * 0.7, final_value * 1.1),
                   arrowprops=dict(arrowstyle='->', color='black', lw=1.5),
                   fontsize=10,
                   bbox=dict(boxstyle='round,pad=0.5', facecolor='yellow', alpha=0.7))
    
    plt.tight_layout()
    
    # Save and show
    plt.savefig('retirement_projection.png', dpi=150, bbox_inches='tight')
    print("\nVisualization saved as 'retirement_projection.png'")
    plt.show()


def calculate_break_even_year(
    retirement_goal: float,
    inflation_rate: float,
    years_until_retirement: int,
    roth_trajectory: tuple = None,
    inheritance_trajectory: tuple = None
) -> int:
    """
    Calculate the year when total assets reach the retirement goal.
    
    Returns:
        Year when goal is reached, or None if never reached
    """
    # Calculate goal trajectory (grows with inflation)
    # retirement_goal is the goal AT RETIREMENT, so we need to work backwards
    goal_today = retirement_goal / ((1 + inflation_rate) ** years_until_retirement)
    goal_trajectory = []
    for year in range(years_until_retirement + 1):
        # Goal grows with inflation each year from today
        goal_value = goal_today * ((1 + inflation_rate) ** year)
        goal_trajectory.append(goal_value)
    
    # Calculate total assets trajectory
    if roth_trajectory and inheritance_trajectory:
        roth_years, roth_balances = roth_trajectory
        inh_years, inh_values = inheritance_trajectory
        min_len = min(len(roth_balances), len(inh_values))
        total_assets = [roth_balances[i] + inh_values[i] for i in range(min_len)]
    elif roth_trajectory:
        _, total_assets = roth_trajectory
    elif inheritance_trajectory:
        _, total_assets = inheritance_trajectory
    else:
        return None
    
    # Find when assets cross goal
    for year in range(min(len(total_assets), len(goal_trajectory))):
        if total_assets[year] >= goal_trajectory[year]:
            return year
    
    return None  # Never reached


def export_to_csv(
    filename: str,
    retirement_goal: float,
    inflation_rate: float,
    years_until_retirement: int,
    roth_trajectory: tuple = None,
    inheritance_trajectory: tuple = None
):
    """Export year-by-year data to CSV file."""
    # Calculate goal trajectory (grows with inflation)
    # retirement_goal is the goal AT RETIREMENT, so we need to work backwards
    goal_today = retirement_goal / ((1 + inflation_rate) ** years_until_retirement)
    goal_trajectory = []
    for year in range(years_until_retirement + 1):
        goal_value = goal_today * ((1 + inflation_rate) ** year)
        goal_trajectory.append(goal_value)
    
    # Prepare data
    years = list(range(years_until_retirement + 1))
    roth_balances = [0] * len(years)
    inheritance_values = [0] * len(years)
    total_assets = [0] * len(years)
    
    if roth_trajectory:
        roth_years, roth_balances_list = roth_trajectory
        for i, year in enumerate(roth_years):
            if year < len(roth_balances):
                roth_balances[year] = roth_balances_list[i]
    
    if inheritance_trajectory:
        inh_years, inh_values_list = inheritance_trajectory
        for i, year in enumerate(inh_years):
            if year < len(inheritance_values):
                inheritance_values[year] = inh_values_list[i]
    
    # Calculate total assets
    for i in range(len(years)):
        total_assets[i] = roth_balances[i] + inheritance_values[i]
    
    # Write to CSV
    with open(filename, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Year', 'Years Until Retirement', 'Retirement Goal', 
                        'Roth IRA Balance', 'Inheritance Value', 'Total Assets', 'Shortfall/Surplus'])
        
        for i, year in enumerate(years):
            years_until = years_until_retirement - year
            shortfall = total_assets[i] - goal_trajectory[i]
            writer.writerow([
                year,
                years_until,
                f"{goal_trajectory[i]:,.2f}",
                f"{roth_balances[i]:,.2f}",
                f"{inheritance_values[i]:,.2f}",
                f"{total_assets[i]:,.2f}",
                f"{shortfall:,.2f}"
            ])
    
    print(f"\nData exported to '{filename}'")


def save_scenario(filename: str, scenario_data: dict):
    """Save scenario to JSON file."""
    with open(filename, 'w') as f:
        json.dump(scenario_data, f, indent=2)
    print(f"\nScenario saved to '{filename}'")


def load_scenario(filename: str) -> dict:
    """Load scenario from JSON file."""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"\nError: File '{filename}' not found.")
        return None
    except json.JSONDecodeError:
        print(f"\nError: Invalid JSON in '{filename}'.")
        return None


def main():
    """Main function to run the retirement calculator."""
    print("Retirement Savings Goal Calculator")
    print("-" * 60)
    
    # Check for load scenario
    load_choice = input("\nLoad saved scenario? (y/n): ").strip().lower()
    scenario_data = None
    
    if load_choice == 'y':
        filename = input("Enter scenario filename: ").strip()
        scenario_data = load_scenario(filename)
        if scenario_data is None:
            return
    
    # Get user inputs
    try:
        # Retirement goal inputs
        print("\n--- Retirement Goal Inputs ---")
        if scenario_data:
            desired_income = scenario_data.get('desired_income', 0)
            inflation_rate = scenario_data.get('inflation_rate', 0) / 100 if isinstance(scenario_data.get('inflation_rate'), (int, float)) else scenario_data.get('inflation_rate', 0)
            years = scenario_data.get('years_until_retirement', 0)
            withdrawal_rate = scenario_data.get('withdrawal_rate', 0.03) / 100 if isinstance(scenario_data.get('withdrawal_rate'), (int, float)) else scenario_data.get('withdrawal_rate', 0.03)
            social_security = scenario_data.get('social_security', 0)
            print(f"Loaded: Income=${desired_income:,.0f}, Inflation={inflation_rate*100:.1f}%, Years={years}, SS=${social_security:,.0f}")
        else:
            desired_income = float(input("Enter desired annual income (today's dollars): $"))
            inflation_rate = float(input("Enter assumed annual inflation rate (e.g., 3.0 for 3%): ")) / 100
            years = int(input("Enter years until retirement: "))
            
            # Optional: allow custom withdrawal rate
            custom_rate = input("Enter withdrawal rate (press Enter for default 3%): ").strip()
            withdrawal_rate = float(custom_rate) / 100 if custom_rate else 0.03
            
            # Social Security input
            ss_input = input("Enter estimated annual Social Security benefit (today's dollars, press Enter for $0): ").strip()
            social_security = float(ss_input) if ss_input else 0.0
        
        # Perform retirement goal calculation
        retirement_results = calculate_retirement_goal(
            desired_annual_income=desired_income,
            inflation_rate=inflation_rate,
            years_until_retirement=years,
            withdrawal_rate=withdrawal_rate,
            social_security_annual=social_security
        )
        
        # Print retirement goal results
        print_retirement_goal(retirement_results)
        
        # Track assets for summary and visualization
        roth_balance = None
        inheritance_value = None
        roth_trajectory = None
        inheritance_trajectory = None
        
        # Roth IRA inputs
        print("\n--- Roth IRA Projection Inputs ---")
        if scenario_data and 'roth_ira' in scenario_data:
            roth_data = scenario_data['roth_ira']
            current_balance = roth_data.get('current_balance', 0)
            annual_contribution = roth_data.get('annual_contribution', 0)
            annual_return = roth_data.get('annual_return', 0) / 100 if isinstance(roth_data.get('annual_return'), (int, float)) else roth_data.get('annual_return', 0)
            include_roth = 'y'
            print(f"Loaded: Balance=${current_balance:,.0f}, Contribution=${annual_contribution:,.0f}, Return={annual_return*100:.1f}%")
        else:
            include_roth = input("Would you like to model Roth IRA growth? (y/n): ").strip().lower()
            
            if include_roth == 'y':
                current_balance = float(input("Enter current Roth IRA balance: $"))
                annual_contribution = float(input("Enter annual Roth IRA contribution: $"))
                annual_return = float(input("Enter assumed annual return rate (e.g., 7.0 for 7%): ")) / 100
            
            # Perform Roth IRA calculation
            roth_results = calculate_roth_ira_growth(
                current_balance=current_balance,
                annual_contribution=annual_contribution,
                annual_return_rate=annual_return,
                years=years
            )
            
            # Calculate trajectory for visualization
            roth_trajectory = calculate_roth_ira_trajectory(
                current_balance=current_balance,
                annual_contribution=annual_contribution,
                annual_return_rate=annual_return,
                years=years
            )
            
            # Print Roth IRA results with comparison to retirement goal
            print_roth_ira_results(
                roth_results, 
                retirement_goal=retirement_results['required_portfolio_balance']
            )
            
            roth_balance = roth_results['total_projected_balance']
        
        # Inheritance inputs
        print("\n--- Inheritance Projection Inputs ---")
        if scenario_data and 'inheritance' in scenario_data:
            inh_data = scenario_data['inheritance']
            mother_portfolio = inh_data.get('mother_portfolio', 0)
            inheritance_growth = inh_data.get('growth_rate', 0) / 100 if isinstance(inh_data.get('growth_rate'), (int, float)) else inh_data.get('growth_rate', 0)
            years_until_inheritance = inh_data.get('years_until_inheritance', 0)
            num_beneficiaries = inh_data.get('number_of_beneficiaries', 3)
            include_inheritance = 'y'
            print(f"Loaded: Portfolio=${mother_portfolio:,.0f}, Growth={inheritance_growth*100:.1f}%, Years={years_until_inheritance}, Beneficiaries={num_beneficiaries}")
        else:
            include_inheritance = input("Would you like to model inheritance? (y/n): ").strip().lower()
            
            if include_inheritance == 'y':
                mother_portfolio = float(input("Enter mother's current portfolio value: $"))
                inheritance_growth = float(input("Enter assumed growth rate for inheritance (e.g., 5.0 for 5%): ")) / 100
                years_until_inheritance = int(input("Enter years until inheritance is received: "))
                
                # Optional: number of beneficiaries (default 3)
                beneficiaries_input = input("Enter number of beneficiaries (press Enter for default 3): ").strip()
                num_beneficiaries = int(beneficiaries_input) if beneficiaries_input else 3
            
            # Perform inheritance calculation
            inheritance_results = calculate_inheritance_projection(
                mother_portfolio_value=mother_portfolio,
                growth_rate=inheritance_growth,
                years_until_inheritance=years_until_inheritance,
                years_until_retirement=years,
                number_of_beneficiaries=num_beneficiaries
            )
            
            # Calculate trajectory for visualization
            inheritance_trajectory = calculate_inheritance_trajectory(
                mother_portfolio_value=mother_portfolio,
                growth_rate=inheritance_growth,
                years_until_inheritance=years_until_inheritance,
                years_until_retirement=years,
                number_of_beneficiaries=num_beneficiaries
            )
            
            # Print inheritance results with comparison to retirement goal
            print_inheritance_results(
                inheritance_results,
                retirement_goal=retirement_results['required_portfolio_balance']
            )
            
            inheritance_value = inheritance_results['value_at_retirement']
        
        # Print total assets summary
        if roth_balance is not None or inheritance_value is not None:
            print_total_assets_summary(
                retirement_goal=retirement_results['required_portfolio_balance'],
                withdrawal_rate=retirement_results['withdrawal_rate'],
                inflation_rate=retirement_results['inflation_rate'],
                years_until_retirement=retirement_results['years_until_retirement'],
                roth_balance=roth_balance,
                inheritance_value=inheritance_value
            )
        
        # Break-even year calculation
        if roth_trajectory is not None or inheritance_trajectory is not None:
            break_even = calculate_break_even_year(
                retirement_goal=retirement_results['required_portfolio_balance'],
                inflation_rate=inflation_rate,
                years_until_retirement=years,
                roth_trajectory=roth_trajectory,
                inheritance_trajectory=inheritance_trajectory
            )
            
            if break_even is not None:
                years_until_break_even = years - break_even
                print(f"\n{'='*60}")
                print(f"BREAK-EVEN ANALYSIS")
                print(f"{'='*60}")
                print(f"  You will reach your retirement goal in {break_even} years")
                print(f"  ({years_until_break_even} years before your target retirement date)")
                if years_until_break_even > 0:
                    print(f"  This means you could potentially retire {years_until_break_even} years early!")
                print(f"{'='*60}\n")
            else:
                print(f"\n{'='*60}")
                print(f"BREAK-EVEN ANALYSIS")
                print(f"{'='*60}")
                print(f"  Your projected assets will not reach the retirement goal")
                print(f"  by your target retirement date.")
                print(f"{'='*60}\n")
        
        # Visualization
        if roth_trajectory is not None or inheritance_trajectory is not None:
            print("\n--- Visualization ---")
            show_plot = input("Would you like to see a visualization? (y/n): ").strip().lower()
            if show_plot == 'y':
                create_retirement_visualization(
                    retirement_goal=retirement_results['required_portfolio_balance'],
                    years_until_retirement=years,
                    inflation_rate=inflation_rate,
                    roth_trajectory=roth_trajectory,
                    inheritance_trajectory=inheritance_trajectory
                )
        
        # CSV Export
        if roth_trajectory is not None or inheritance_trajectory is not None:
            print("\n--- Export Data ---")
            export_choice = input("Export year-by-year data to CSV? (y/n): ").strip().lower()
            if export_choice == 'y':
                csv_filename = input("Enter CSV filename (press Enter for 'retirement_data.csv'): ").strip()
                if not csv_filename:
                    csv_filename = 'retirement_data.csv'
                export_to_csv(
                    filename=csv_filename,
                    retirement_goal=retirement_results['required_portfolio_balance'],
                    inflation_rate=inflation_rate,
                    years_until_retirement=years,
                    roth_trajectory=roth_trajectory,
                    inheritance_trajectory=inheritance_trajectory
                )
        
        # Save scenario
        print("\n--- Save Scenario ---")
        save_choice = input("Save this scenario? (y/n): ").strip().lower()
        if save_choice == 'y':
            scenario_filename = input("Enter scenario filename (press Enter for 'scenario.json'): ").strip()
            if not scenario_filename:
                scenario_filename = 'scenario.json'
            
            # Collect all scenario data
            scenario_data = {
                'desired_income': desired_income,
                'inflation_rate': inflation_rate,
                'years_until_retirement': years,
                'withdrawal_rate': withdrawal_rate,
                'social_security': social_security,
                'timestamp': datetime.now().isoformat()
            }
            
            if roth_balance is not None:
                scenario_data['roth_ira'] = {
                    'current_balance': current_balance if 'current_balance' in locals() else 0,
                    'annual_contribution': annual_contribution if 'annual_contribution' in locals() else 0,
                    'annual_return': annual_return if 'annual_return' in locals() else 0
                }
            
            if inheritance_value is not None:
                scenario_data['inheritance'] = {
                    'mother_portfolio': mother_portfolio if 'mother_portfolio' in locals() else 0,
                    'growth_rate': inheritance_growth if 'inheritance_growth' in locals() else 0,
                    'years_until_inheritance': years_until_inheritance if 'years_until_inheritance' in locals() else 0,
                    'number_of_beneficiaries': num_beneficiaries if 'num_beneficiaries' in locals() else 3
                }
            
            save_scenario(scenario_filename, scenario_data)
        
    except ValueError as e:
        print(f"\nError: Invalid input. Please enter numeric values.\n{e}")
    except KeyboardInterrupt:
        print("\n\nCalculation cancelled by user.")
    except Exception as e:
        print(f"\nError: {e}")


if __name__ == "__main__":
    main()

