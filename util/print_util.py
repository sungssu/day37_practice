# ptint_util.py

# 출력시 구분선과 함께 출력하는 함수
def pp(*obj):
    print(*obj)
    print('-' * 80)

# 위로 몇 줄 출력결과창 올리기 위한 함구
def up(n):
    print('\n' * n)

# 타입과 구분선을 함께 출력하는 함수
def pt(*args):
    print(type(*args))
    pl(80)

# 개수만큼 구분선을 출력하는 함수
def pl(n):
    print('-' * n)