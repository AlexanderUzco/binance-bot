const colors = {
    green: '\x1b[32m',
    red: '\x1b[31m',
    gray: '\x1b[90m',
};

// Log a message with a color
const logColor = (color: string, message:string) => {
    console.log(color, message, colors.gray);
};

// Log a message
const log = (message: string) => {
    console.log(message);
};

export {
    logColor,
    log,
    colors,
}