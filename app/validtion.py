async def validation_phone(number):
    if number[0] == '8' or number[0:2] == '+7' or number[0] == '7':
        if len(number) == 12 or len(number) == 11:
            return True
    else:
        return False