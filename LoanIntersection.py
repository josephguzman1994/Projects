import numpy as np
import matplotlib.pyplot as plt
from dataclasses import dataclass
from typing import List

@dataclass
class Loan:
    monthly_payment: float
    interest_rate: float  # Annual interest rate as decimal (e.g., 0.05 for 5%)
    remaining_balance: float
    name: str = ""  # Optional name for the loan

class LoanVisualizer:
    def __init__(self, loans: List[Loan]):
        self.loans = loans
    
    def calculate_total_paid(self, months: int) -> np.ndarray:
        """Calculate cumulative amount paid for all loans up to specified months."""
        total_paid = np.zeros(months)
        
        for loan in self.loans:
            payments = self._calculate_loan_payments(loan, months)
            total_paid += np.cumsum(payments)
            
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
        
        # Calculate total payout amounts
        existing_final = existing_total[-1]
        new_final = new_total[-1]
        total_difference = new_final - existing_final
        
        # Find intersection point
        diff = existing_total - new_total
        intersection_idx = np.where(np.diff(np.signbit(diff)))[0]
        
        # Create the plot
        plt.figure(figsize=(12, 8))
        
        # Plot individual existing loans and their payoff points
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
        plt.plot(time, new_total, 'r-', linewidth=2,
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
            
            print(f"\nFinal Payout Comparison:")
            print(f"  Current loans total payout: ${existing_final:,.2f}")
            print(f"  New loan total payout:     ${new_final:,.2f}")
            print(f"  Difference:                ${abs(total_difference):,.2f}")
            print(f"  The {'new' if total_difference > 0 else 'current'} plan will cost",
                  f"${abs(total_difference):,.2f} {'more' if total_difference > 0 else 'less'} overall")
            
            # Calculate monthly payment comparison
            current_monthly = sum(loan.monthly_payment for loan in self.loans)
            print(f"\nMonthly Payment Comparison:")
            print(f"  Current total monthly payment: ${current_monthly:,.2f}")
            print(f"  New monthly payment:          ${new_loan.monthly_payment:,.2f}")
            print(f"  Monthly payment difference:   ${abs(new_loan.monthly_payment - current_monthly):,.2f}")
            print(f"  The new plan will cost ${abs(new_loan.monthly_payment - current_monthly):,.2f}",
                  f"{'more' if new_loan.monthly_payment > current_monthly else 'less'} per month")
        
        plt.xlabel('Months')
        plt.ylabel('Cumulative Amount Paid ($)')
        plt.title('Loan Comparison: Current Loans vs New Loan')
        plt.grid(True)
        plt.legend()
        plt.show()

# Example usage
if __name__ == "__main__":
    # Example current loans
    current_loans = [
        Loan(monthly_payment=1900, interest_rate=0.0575, 
             remaining_balance=71000, name="Mortgage 1"),
        Loan(monthly_payment=700, interest_rate=0.05375, 
             remaining_balance=50000, name="Mortgage 2"),
        #Loan(monthly_payment=400, interest_rate=0.09, 
        #     remaining_balance=40000, name="House Remodeling")
    ]
    
    visualizer = LoanVisualizer(current_loans)
    
    # Calculate and print the actual term length for each loan
    for loan in current_loans:
        months = visualizer.calculate_loan_term(loan)
        print(f"\n{loan.name}:")
        print(f"Monthly payment: ${loan.monthly_payment:,.2f}")
        print(f"Interest rate: {loan.interest_rate*100:.1f}%")
        print(f"Remaining balance: ${loan.remaining_balance:,.2f}")
        print(f"Will be paid off in {months/12:.1f} years ({months} months)")
    
    # Define new loan parameters manually
    new_balance = 200000  # Manually defined refinance amount
    new_rate = 0.075     # 7.5% APR
    new_term_months = 360  # 30 years
    
    # Calculate the required monthly payment for the new loan
    required_payment = visualizer.calculate_monthly_payment(new_balance, new_rate, new_term_months)
    
    print(f"\nRefinanced Loan Details:")
    print(f"Loan amount: ${new_balance:,.2f}")
    print(f"Interest rate: {new_rate*100:.1f}%")
    print(f"Term length: {new_term_months/12:.0f} years")
    print(f"Required monthly payment: ${required_payment:,.2f}")
    
    new_loan = Loan(
        monthly_payment=required_payment,
        interest_rate=new_rate,
        remaining_balance=new_balance,
        name="Refinanced Loan"
    )
    
    visualizer.plot_comparison(new_loan)