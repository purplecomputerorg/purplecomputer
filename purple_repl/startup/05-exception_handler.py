"""
Kid-friendly exception handler for Purple Computer
Replaces scary tracebacks with friendly messages
"""

def kid_friendly_exception_handler(shell, etype, evalue, tb, tb_offset=None):
    """Custom exception handler that shows friendly messages instead of tracebacks"""

    # NameError - when they type something undefined
    if etype.__name__ == 'NameError':
        # Extract the name from the error message
        error_msg = str(evalue)
        if "'" in error_msg:
            name = error_msg.split("'")[1]
            print(f"\n💭 Hmm, I don't know '{name}' yet.\n")
        else:
            print("\n💭 Hmm, I don't know that yet.\n")
        return

    # SyntaxError - when they make a typo or invalid syntax
    elif etype.__name__ == 'SyntaxError':
        print("\n🤔 I don't understand that. Try again!\n")
        return

    # ZeroDivisionError - division by zero
    elif etype.__name__ == 'ZeroDivisionError':
        print("\n🙈 Oops! You can't divide by zero. Try a different number!\n")
        return

    # TimeoutError - infinite loops (from our timeout handler)
    elif etype.__name__ == 'TimeoutError':
        print(f"\n{evalue}\n")
        return

    # TypeError - wrong type of arguments
    elif etype.__name__ == 'TypeError':
        print("\n🤷 That doesn't work together. Try something else!\n")
        return

    # AttributeError - trying to access something that doesn't exist
    elif etype.__name__ == 'AttributeError':
        print("\n🔍 That thing doesn't have that property.\n")
        return

    # IndexError / KeyError - out of bounds
    elif etype.__name__ in ('IndexError', 'KeyError'):
        print("\n📦 That's not in there. Try a different index!\n")
        return

    # Everything else - generic friendly message
    else:
        print("\n✨ Something unexpected happened. Let's try something else!\n")
        return


# Install the custom exception handler
ip = get_ipython()
if ip:
    ip.set_custom_exc((BaseException,), kid_friendly_exception_handler)
