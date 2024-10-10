const express = require('express');
const nodemailer = require('nodemailer');
const multer = require('multer');
const fs = require('fs');

const app = express();
const upload = multer({ dest: 'uploads/' });

app.post('/send-pdf', upload.single('pdf'), async (req, res) => {
    const email = req.body.email;
    const pdfPath = req.file.path;

    // Configure nodemailer
    const transporter = nodemailer.createTransport({
        service: 'gmail',
        auth: {
            user: 'your-email@gmail.com',
            pass: 'your-email-password'
        }
    });

    const mailOptions = {
        from: 'your-email@gmail.com',
        to: email,
        subject: 'Your Health Tracker PDF',
        text: 'Please find attached your health tracker PDF.',
        attachments: [
            {
                filename: 'health_tracker.pdf',
                path: pdfPath
            }
        ]
    };

    try {
        await transporter.sendMail(mailOptions);
        res.send('Email sent!');
    } catch (error) {
        console.error(error);
        res.status(500).send('Failed to send email.');
    } finally {
        // Clean up the uploaded file
        fs.unlinkSync(pdfPath);
    }
});

// Start the server
app.listen(3000, () => {
    console.log('Server is running on port 3000');
});