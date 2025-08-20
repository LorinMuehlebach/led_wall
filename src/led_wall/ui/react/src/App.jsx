// App.jsx
import React from 'react';

export default function App({ title = '', onClick }) {
    return (
        <>
            <b>Hello {title}</b>
            <button onClick={() => onClick('Button clicked!')}>Click Me</button>
        </>
    );
}