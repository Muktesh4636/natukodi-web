import sys

with open('accounts_views_server.py', 'r') as f:
    lines = f.readlines()

new_lines = []
skip = False
for i, line in enumerate(lines):
    if 'def initiate_withdraw(request):' in line:
        new_lines.append(line)
        new_lines.append('    """Create a withdraw request with PENDING status - supports both bank_detail_id and manual details"""\n')
        new_lines.append('    amount_raw = request.data.get(\'amount\')\n')
        new_lines.append('    withdrawal_method = request.data.get(\'withdrawal_method\', \'\').strip()\n')
        new_lines.append('    withdrawal_details = request.data.get(\'withdrawal_details\', \'\').strip()\n')
        new_lines.append('    bank_detail_id = request.data.get(\'bank_detail_id\')\n')
        new_lines.append('\n')
        new_lines.append('    try:\n')
        new_lines.append('        amount = _parse_amount(amount_raw)\n')
        new_lines.append('    except ValueError as exc:\n')
        new_lines.append('        return Response({\'error\': str(exc)}, status=400)\n')
        new_lines.append('\n')
        new_lines.append('    # If bank_detail_id is provided, use it to populate method and details\n')
        new_lines.append('    if bank_detail_id:\n')
        new_lines.append('        try:\n')
        new_lines.append('            bank_detail = UserBankDetail.objects.get(id=bank_detail_id, user=request.user)\n')
        new_lines.append('            withdrawal_method = "BANK" if bank_detail.account_number else "UPI"\n')
        new_lines.append('            if bank_detail.account_number:\n')
        new_lines.append('                withdrawal_details = f"Acc: {bank_detail.account_number}, IFSC: {bank_detail.ifsc_code}, Name: {bank_detail.account_name}"\n')
        new_lines.append('            else:\n')
        new_lines.append('                withdrawal_details = f"UPI: {bank_detail.upi_id}, Name: {bank_detail.account_name}"\n')
        new_lines.append('        except UserBankDetail.DoesNotExist:\n')
        new_lines.append('            return Response({\'error\': \'Bank detail not found\'}, status=404)\n')
        new_lines.append('\n')
        new_lines.append('    if not withdrawal_method or not withdrawal_details:\n')
        new_lines.append('        return Response({\'error\': \'Withdrawal method and details are required\'}, status=400)\n')
        new_lines.append('\n')
        new_lines.append('    try:\n')
        new_lines.append('        with db_transaction.atomic():\n')
        new_lines.append('            wallet = Wallet.objects.select_for_update().get(user=request.user)\n')
        new_lines.append('            if wallet.withdrawable_balance < amount:\n')
        new_lines.append('                return Response({\'error\': f\'Insufficient withdrawable balance. Available: {wallet.withdrawable_balance}\'}, status=400)\n')
        new_lines.append('\n')
        new_lines.append('            withdraw = WithdrawRequest.objects.create(\n')
        new_lines.append('                user=request.user, \n')
        new_lines.append('                amount=amount, \n')
        new_lines.append('                withdrawal_method=withdrawal_method, \n')
        new_lines.append('                withdrawal_details=withdrawal_details, \n')
        new_lines.append('                status=\'PENDING\'\n')
        new_lines.append('            )\n')
        new_lines.append('            \n')
        new_lines.append('            # Deduct from wallet and move to unavaliable (locked for withdrawal)\n')
        new_lines.append('            wallet.unavaliable_balance += amount\n')
        new_lines.append('            wallet.balance -= amount\n')
        new_lines.append('            wallet.save()\n')
        new_lines.append('\n')
        new_lines.append('            # Update Redis cache if needed\n')
        new_lines.append('            try:\n')
        new_lines.append('                cache_user_session(request.user, wallet.balance)\n')
        new_lines.append('            except: pass\n')
        new_lines.append('\n')
        new_lines.append('            return Response(WithdrawRequestSerializer(withdraw, context={\'request\': request}).data, status=201)\n')
        new_lines.append('    except Exception as e:\n')
        new_lines.append('        return Response({\'error\': f\'Failed to create withdrawal request: {str(e)}\'}, status=500)\n')
        
        # Skip the old implementation
        skip = True
        continue
    
    if skip:
        if line.startswith('def ') or line.startswith('@api_view'):
            skip = False
            new_lines.append(line)
        continue
    
    new_lines.append(line)

with open('accounts_views_fixed.py', 'w') as f:
    f.writelines(new_lines)
