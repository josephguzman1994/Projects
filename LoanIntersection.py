import numpy as np
import matplotlib.pyplot as plt
import tkinter as tk
from tkinter import ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from dataclasses import dataclass
from typing import List

@dataclass
class Loan:
    monthly_payment: float
    interest_rate: float  # Annual interest rate as decimal (e.g., 0.05 for 5%)
    remaining_balance: float
    name: str = ""  # Optional name for the loan
    escrow: float = 0.0 # Optional monthly escrow amount

class LoanVisualizer:
    def __init__(self, loans: List[Loan]):
        self.loans = loans
    
    def calculate_total_paid(self, months: int) -> np.ndarray:
        """Calculate cumulative amount paid for all loans up to specified months."""
        total_paid = np.zeros(months)
        
        for loan in self.loans:
            # Calculate the actual term for this loan
            loan_term = self.calculate_loan_term(loan)
            
            # Calculate payments up to the loan term
            payments = self._calculate_loan_payments(loan, months)
            total_paid += np.cumsum(payments)
            
            # Add escrow payments only until the loan term
            if loan.escrow > 0:
                escrow_payments = np.zeros(months)
                escrow_payments[:loan_term] = loan.escrow
                total_paid += np.cumsum(escrow_payments)
        
        return total_paid

    def calculate_loan_term(self, loan: Loan) -> int:
        """Calculate the number of months needed to pay off the loan."""
        balance = loan.remaining_balance
        monthly_rate = loan.interest_rate / 12
        months = 0
        
        while balance > 0 and months < 1200:  # 1200 months = 100 years as safety limit
            interest = balance * monthly_rate
            payment = min(loan.monthly_payment, balance + interest)
            balance = balance + interest - payment
            months += 1
            
        return months
    
    def calculate_loan_term_from_payment(self, principal: float, annual_rate: float, monthly_payment: float) -> int:
        """Calculate the remaining term length given the principal, rate, and monthly payment."""
        if annual_rate == 0:
            return int(principal / monthly_payment)
            
        monthly_rate = annual_rate / 12
        
        # Using the amortization formula, solved for n (number of months):
        # P = L[c(1 + c)^n]/[(1 + c)^n - 1]
        # where P = monthly payment, L = principal, c = monthly rate, n = number of months
        
        if monthly_payment <= principal * monthly_rate:
            return float('inf')  # Payment is too small to ever pay off loan
            
        n = np.log(monthly_payment / (monthly_payment - principal * monthly_rate)) / np.log(1 + monthly_rate)
        return int(np.ceil(n))

    def calculate_amortization_schedule(self, loan: Loan, months: int) -> tuple[float, float, float]:
        """Calculate principal, interest, and remaining balance at a given month."""
        balance = loan.remaining_balance
        monthly_rate = loan.interest_rate / 12
        total_interest = 0
        total_principal = 0
        
        for month in range(months):
            if balance <= 0:
                break
                
            # Calculate interest for this month
            interest = balance * monthly_rate
            
            # Apply payment
            payment = min(loan.monthly_payment, balance + interest)
            principal = payment - interest
            
            # Update totals
            total_interest += interest
            total_principal += principal
            balance = balance - principal
            
        return total_principal, total_interest, balance

    def _calculate_loan_payments(self, loan: Loan, months: int) -> np.ndarray:
        """Calculate monthly payments including interest for a single loan."""
        payments = np.zeros(months)
        balance = loan.remaining_balance
        monthly_rate = loan.interest_rate / 12
        
        for month in range(months):
            if balance <= 0:
                break
                
            # Calculate interest for this month
            interest = balance * monthly_rate
            
            # Apply payment
            payment = min(loan.monthly_payment, balance + interest)
            payments[month] = payment
            
            # Update balance
            balance = balance + interest - payment
            
        return payments
    
    def calculate_monthly_payment(self, principal: float, annual_rate: float, months: int) -> float:
        """Calculate the monthly payment for an amortized loan."""
        if annual_rate == 0:
            return principal / months
            
        monthly_rate = annual_rate / 12
        return principal * (monthly_rate * (1 + monthly_rate)**months) / ((1 + monthly_rate)**months - 1)

    def plot_comparison(self, new_loan: Loan):
        """Compare existing loans vs a new refinanced loan."""
        # Calculate the actual term length for each loan
        loan_terms = [self.calculate_loan_term(loan) for loan in self.loans]
        new_loan_term = self.calculate_loan_term(new_loan)
        
        # Find the maximum time period to analyze
        months = max(new_loan_term, max(loan_terms))
        time = np.arange(months)
        
        # Calculate payments for existing loans
        existing_total = self.calculate_total_paid(months)
        
        # Calculate payments for new loan
        new_payments = self._calculate_loan_payments(new_loan, months)
        new_total = np.cumsum(new_payments)
        new_total_with_escrow = new_total + (new_loan.escrow * np.arange(1, months + 1))
        
         # Calculate final amounts
        existing_final = existing_total[-1]
        new_final = new_total_with_escrow[-1]
        total_difference = new_final - existing_final
        
        # Find intersection point
        diff = existing_total - new_total_with_escrow
        intersection_idx = np.where(np.diff(np.signbit(diff)))[0]
        
        # Create the plot
        plt.figure(figsize=(12, 8))
        
        # Plot individual existing loans
        for loan, term in zip(self.loans, loan_terms):
            payments = self._calculate_loan_payments(loan, months)
            cumulative = np.cumsum(payments)
            label = f"{loan.name} (${loan.remaining_balance:,.0f} @ {loan.interest_rate*100:.1f}% APR)"
            line = plt.plot(time, cumulative, '--', alpha=0.5, label=label)[0]
            
            # Add payoff point annotation
            payoff_amount = cumulative[term-1]
            plt.plot(term, payoff_amount, 'ko', alpha=0.5, markersize=4)
            plt.annotate(
                f"{loan.name}\n{term/12:.1f}y (${loan.monthly_payment:,.0f}/mo)",
                (term, payoff_amount),
                xytext=(5, 5), textcoords='offset points',
                fontsize=8,
                bbox=dict(boxstyle='round,pad=0.3', fc='lightgray', alpha=0.3),
                arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0.2'),
                color=line.get_color()
            )
        
        # Plot totals with final amounts in labels
        plt.plot(time, existing_total, 'b-', linewidth=2, 
                label=f'Current Total (Final: ${existing_final:,.0f})')
        plt.plot(time, new_total_with_escrow, 'r-', linewidth=2,
                label=f'New Loan @ {new_loan.interest_rate*100:.1f}% (Final: ${new_final:,.0f})')
        
       # Mark intersection point if it exists
        if len(intersection_idx) > 0:
            intersect_month = intersection_idx[0]
            intersect_amount = existing_total[intersect_month]
            
            # Calculate amortization details at break-even
            principal_paid, interest_paid, remaining_balance = self.calculate_amortization_schedule(
                new_loan, intersect_month)
            
            plt.plot(intersect_month, intersect_amount, 'ko', markersize=10)
            plt.annotate(
                f'Break-even point:\nMonth {intersect_month} ({intersect_month/12:.1f}y)\n'
                f'Total paid: ${intersect_amount:,.0f}\n'
                f'Remaining: ${remaining_balance:,.0f}',
                (intersect_month, intersect_amount),
                xytext=(30, 30), textcoords='offset points',
                bbox=dict(boxstyle='round,pad=0.5', fc='yellow', alpha=0.5),
                arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0.3'))
            
            # Print detailed analysis
            years = intersect_month / 12
            print(f"\nBreak-even Analysis:")
            print(f"Break-even occurs at {years:.1f} years (month {intersect_month})")
            print(f"Total paid at break-even: ${intersect_amount:,.2f}")
            print(f"\nRefinanced Loan Status at Break-even:")
            print(f"  Original balance:     ${new_loan.remaining_balance:,.2f}")
            print(f"  Principal paid:       ${principal_paid:,.2f}")
            print(f"  Interest paid:        ${interest_paid:,.2f}")
            print(f"  Remaining balance:    ${remaining_balance:,.2f}")
            print(f"  Principal reduction:  {(principal_paid/new_loan.remaining_balance)*100:.1f}%")
        
        plt.xlabel('Months')
        plt.ylabel('Cumulative Amount Paid ($)')
        plt.title('Loan Comparison')
        plt.grid(True)
        plt.legend()
        plt.show()

    def interactive_analysis_window(self, new_loan: Loan):
        """Launch an interactive window to analyze costs at different points in time."""
        # Create main window
        root = tk.Tk()
        root.title("Loan Cost Analysis")
        root.geometry("1000x800")

        # Create frame for controls
        control_frame = ttk.Frame(root)
        control_frame.pack(fill='x', padx=10, pady=5)

        # Calculate loan terms and time period
        loan_terms = [self.calculate_loan_term(loan) for loan in self.loans]
        new_loan_term = self.calculate_loan_term(new_loan)
        months = max(new_loan_term, max(loan_terms))
        time = np.arange(months)

        # Calculate payment trajectories
        existing_total = self.calculate_total_paid(months)
        new_payments = self._calculate_loan_payments(new_loan, months)
        new_total = np.cumsum(new_payments)
        
        # Add escrow to new loan total payments
        new_total_with_escrow = new_total + (new_loan.escrow * np.arange(1, months + 1))

        # Calculate remaining balances for each month
        existing_balances = np.zeros(months)
        new_balance = np.zeros(months)

        # Calculate remaining balance for existing loans
        for month in range(months):
            balance_sum = 0
            for loan in self.loans:
                _, _, remaining = self.calculate_amortization_schedule(loan, month + 1)
                balance_sum += remaining
            existing_balances[month] = balance_sum
            
            # Calculate remaining balance for new loan
            _, _, new_remaining = self.calculate_amortization_schedule(new_loan, month + 1)
            new_balance[month] = new_remaining
        
        # Create matplotlib figure with three subplots
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 12), height_ratios=[2, 1, 1])
        
        # Create canvas
        canvas = FigureCanvasTkAgg(fig, master=root)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Add month slider
        ttk.Label(control_frame, text="Month:").pack(side=tk.LEFT, padx=5)
        month_var = tk.IntVar(value=0)
        month_slider = ttk.Scale(
            control_frame,
            from_=0,
            to=months-1,
            orient='horizontal',
            variable=month_var,
            length=300
        )
        month_slider.pack(side=tk.LEFT, fill='x', expand=True, padx=5)
        
        # Add analysis labels
        analysis_frame = ttk.Frame(root)
        analysis_frame.pack(fill='x', padx=10, pady=5)
        
        month_label = ttk.Label(analysis_frame, text="", font=('Arial', 10))
        month_label.pack(pady=5)
        
        costs_label = ttk.Label(analysis_frame, text="", font=('Arial', 10))
        costs_label.pack(pady=5)

        def update_plot(*args):
            current_month = month_var.get()
            
            # Clear plots
            ax1.clear()
            ax2.clear()
            ax3.clear()

            # Plot cumulative payments (now including escrow)
            ax1.plot(time/12, existing_total, 'b-', label='Current Loans Total')
            ax1.plot(time/12, new_total_with_escrow, 'r-', label='New Loan Total (with Escrow)')
            ax1.axvline(x=current_month/12, color='g', linestyle='--')
            ax1.set_xlabel('Years')
            ax1.set_ylabel('Cumulative Amount Paid ($)')
            ax1.grid(True)
            ax1.legend()

            # Plot cost difference (now including escrow)
            difference = new_total_with_escrow - existing_total
            ax2.plot(time/12, difference, 'k-', label='Cost Difference (New - Current)')
            ax2.axhline(y=0, color='gray', linestyle='-', alpha=0.3)
            ax2.axvline(x=current_month/12, color='g', linestyle='--')
            ax2.set_xlabel('Years')
            ax2.set_ylabel('Cost Difference ($)')
            ax2.grid(True)
            ax2.legend()

            # Plot remaining balances and net worth difference
            ax3.plot(time/12, existing_balances, 'b--', label='Current Loans Balance')
            ax3.plot(time/12, new_balance, 'r--', label='New Loan Balance')
            balance_diff = new_balance - existing_balances
            ax3.plot(time/12, balance_diff, 'k-', label='Balance Difference (New - Current)')
            ax3.axhline(y=0, color='gray', linestyle='-', alpha=0.3)
            ax3.axvline(x=current_month/12, color='g', linestyle='--')
            ax3.set_xlabel('Years')
            ax3.set_ylabel('Remaining Balance ($)')
            ax3.grid(True)
            ax3.legend()

            fig.tight_layout()
            canvas.draw()

            # Update analysis text
            years = current_month / 12
            month_label.config(text=f"Analysis at: {years:.1f} years ({current_month} months)")
            
            current_cost = existing_total[current_month]
            new_cost = new_total_with_escrow[current_month]  # Now includes escrow
            cost_diff = new_cost - current_cost
            
            current_balance = existing_balances[current_month]
            new_remaining = new_balance[current_month]
            balance_difference = new_remaining - current_balance
            
            # Calculate net position (cost difference + balance difference)
            net_position = -(cost_diff + balance_difference)  # Negative because we want to show savings as positive
            
            # Update text display to show escrow details
            costs_label.config(text=(
                f"Current plan total paid: ${current_cost:,.2f}\n"
                f"New plan total paid (with escrow): ${new_cost:,.2f}\n"
                f"Payment difference: ${abs(cost_diff):,.2f} "
                f"({'more' if cost_diff > 0 else 'less'} with new plan)\n"
                f"\nCurrent loans remaining: ${current_balance:,.2f}\n"
                f"New loan remaining: ${new_remaining:,.2f}\n"
                f"Balance difference: ${abs(balance_difference):,.2f} "
                f"({'more' if balance_difference > 0 else 'less'} with new plan)\n"
                f"\nNet worth difference: ${abs(net_position):,.2f} "
                f"({'better' if net_position > 0 else 'worse'} with new plan)\n"
                f"\nMonthly comparison:\n"
                f"Current total payment: ${sum(loan.monthly_payment for loan in self.loans):,.2f}\n"
                f"New total payment (P&I + Escrow): ${new_loan.monthly_payment + new_loan.escrow:,.2f}"
            ))

        # Bind the update function to the slider
        month_var.trace_add('write', update_plot)
        
        # Initial plot
        update_plot()
        
        # Start the GUI event loop
        root.mainloop()

# Example usage
if __name__ == "__main__":
    # First, calculate the P&I portion of the current mortgage payments
    visualizer = LoanVisualizer([])  # Temporary instance to use calculate_monthly_payment
    
    # Mortgage 1 details
    mortgage1_balance = 114506
    mortgage1_rate = 0.06875
    mortgage1_total_payment = 1264.46  # Total payment including escrow
    mortgage1_escrow = 509
    mortgage1_pi = mortgage1_total_payment - mortgage1_escrow  # Get P&I portion

    # Calculate the term length
    mortgage1_term = visualizer.calculate_loan_term_from_payment(
        mortgage1_balance, mortgage1_rate, mortgage1_pi)
    
    # Example current loans with separated P&I and escrow
    current_loans = [
        Loan(monthly_payment=mortgage1_pi,  # Now only P&I
             interest_rate=0.06875, 
             remaining_balance=114506,
             name="Mortgage 1",
             escrow=mortgage1_escrow),  # Add escrow separately
        Loan(monthly_payment=700,
             interest_rate=0.05, 
             remaining_balance=50513.55,
             name="Mortgage 2"),
        #Loan(monthly_payment=440, interest_rate=0.09, 
             #remaining_balance=44000, name="House Remodeling")
    ]
    
    visualizer = LoanVisualizer(current_loans)
    
    # Calculate and print the actual term length for each loan
    for loan in current_loans:
        months = visualizer.calculate_loan_term(loan)
        print(f"\n{loan.name}:")
        print(f"Monthly P&I payment: ${loan.monthly_payment:,.2f}")
        if loan.escrow > 0:
            print(f"Monthly escrow: ${loan.escrow:,.2f}")
            print(f"Total monthly payment: ${loan.monthly_payment + loan.escrow:,.2f}")
        print(f"Interest rate: {loan.interest_rate*100:.1f}%")
        print(f"Remaining balance: ${loan.remaining_balance:,.2f}")
        print(f"Will be paid off in {months/12:.1f} years ({months} months)")
    
    # Define new loan parameters manually
    new_balance = 210000  # Manually defined refinance amount
    new_rate = 0.06875   # 6.875% APR
    new_term_months = 360  # 30 years
    monthly_escrow = 509
    
    # Calculate the required monthly payment for the new loan
    required_payment = visualizer.calculate_monthly_payment(new_balance, new_rate, new_term_months)
    
    print(f"\nRefinanced Loan Details:")
    print(f"Loan amount: ${new_balance:,.2f}")
    print(f"Interest rate: {new_rate*100:.1f}%")
    print(f"Term length: {new_term_months/12:.0f} years")
    print(f"Required P&I payment: ${required_payment:,.2f}")
    print(f"Monthly escrow: ${monthly_escrow:,.2f}")
    print(f"Total monthly payment: ${required_payment + monthly_escrow:,.2f}")
    
    new_loan = Loan(
        monthly_payment=required_payment,
        interest_rate=new_rate,
        remaining_balance=new_balance,
        name="Refinanced Loan",
        escrow=monthly_escrow
    )
    
    visualizer.plot_comparison(new_loan)
    visualizer.interactive_analysis_window(new_loan)