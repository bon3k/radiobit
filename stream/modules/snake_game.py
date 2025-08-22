import asyncio
import random
from PIL import Image, ImageDraw
import RPi.GPIO as GPIO

# Pines
JOYSTICK_UP = 19
JOYSTICK_DOWN = 6
JOYSTICK_LEFT = 5
JOYSTICK_RIGHT = 26
KEY2 = 20
KEY3 = 16

CELL_SIZE = 10
GRID_WIDTH = 24
GRID_HEIGHT = 24

class SnakeGame:
    def __init__(self, lcd):
        self.lcd = lcd
        self.reset_game()

    def reset_game(self):
        self.snake = [(5, 5)]
        self.direction = (1, 0)
        self.food = self.spawn_food()
        self.game_over = False

    def spawn_food(self):
        while True:
            pos = (random.randint(0, GRID_WIDTH - 1), random.randint(0, GRID_HEIGHT - 1))
            if pos not in self.snake:
                return pos

    def change_direction(self, new_dir):
        if (new_dir[0] * -1, new_dir[1] * -1) != self.direction:
            self.direction = new_dir

    def update(self):
        if self.game_over:
            return

        head_x, head_y = self.snake[0]
        dx, dy = self.direction
        new_head = (head_x + dx, head_y + dy)

        if (
            new_head in self.snake or
            not (0 <= new_head[0] < GRID_WIDTH) or
            not (0 <= new_head[1] < GRID_HEIGHT)
        ):
            self.game_over = True
            return

        self.snake.insert(0, new_head)

        if new_head == self.food:
            self.food = self.spawn_food()
        else:
            self.snake.pop()

    def draw(self):
        image = Image.new("RGB", (self.lcd.width, self.lcd.height), "black")
        draw = ImageDraw.Draw(image)

        for x, y in self.snake:
            draw.rectangle([
                x * CELL_SIZE, y * CELL_SIZE,
                (x + 1) * CELL_SIZE - 1, (y + 1) * CELL_SIZE - 1
            ], fill="green")

        fx, fy = self.food
        draw.rectangle([
            fx * CELL_SIZE, fy * CELL_SIZE,
            (fx + 1) * CELL_SIZE - 1, (fy + 1) * CELL_SIZE - 1
        ], fill="red")

        if self.game_over:
#            draw.text((60, 100), "GAME OVER", fill="white")
            pass
        self.lcd.display_image(image)

async def run_snake(lcd):
    GPIO.setmode(GPIO.BCM)
    for pin in [JOYSTICK_UP, JOYSTICK_DOWN, JOYSTICK_LEFT, JOYSTICK_RIGHT, KEY2, KEY3]:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    game = SnakeGame(lcd)

    last_states = {
        JOYSTICK_UP: 1,
        JOYSTICK_DOWN: 1,
        JOYSTICK_LEFT: 1,
        JOYSTICK_RIGHT: 1,
        KEY2: 1,
        KEY3: 1,
    }

    try:
        while True:
            for pin in last_states:
                current = GPIO.input(pin)
                if last_states[pin] == 1 and current == 0:
                    if pin == JOYSTICK_RIGHT:
                        game.change_direction((0, -1))
                        lcd.update_activity()
                    elif pin == JOYSTICK_LEFT:
                        game.change_direction((0, 1))
                        lcd.update_activity()
                    elif pin == JOYSTICK_DOWN:
                        game.change_direction((-1, 0))
                        lcd.update_activity()
                    elif pin == JOYSTICK_UP:
                        game.change_direction((1, 0))
                        lcd.update_activity()
                    elif pin == KEY2 and game.game_over:
                        game.reset_game()
                        lcd.update_activity()
                    elif pin == KEY3:
                        raise KeyboardInterrupt
                last_states[pin] = current

            game.update()
            game.draw()
            await asyncio.sleep(0.1)
    except KeyboardInterrupt:
        image = Image.new("RGB", (lcd.width, lcd.height), "black")
        lcd.display_image(image)


