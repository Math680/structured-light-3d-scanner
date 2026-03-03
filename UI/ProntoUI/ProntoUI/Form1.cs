using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;
using AForge.Video;
using AForge.Video.DirectShow;

namespace ProntoUI
{

    
    public partial class Form1 : Form
    {
        private FilterInfoCollection _videoDevices;
        private VideoCaptureDevice _cam2;

        public Form1()
        {
            InitializeComponent();

            // Important : démarrer/stopper selon l’onglet affiché
            tabControl1.SelectedIndexChanged += TabControl1_SelectedIndexChanged;
            this.FormClosing += Form1_FormClosing;

            // Liste des caméras
            _videoDevices = new FilterInfoCollection(FilterCategory.VideoInputDevice);
            // _videoDevices.Count => nombre de webcams détectées
        }

        private void button1_Click(object sender, EventArgs e)
        {
            
        }

        private void trackBar1_Scroll(object sender, EventArgs e)
        {
            label1.Text = "N = " + trackBar1.Value;
        }

        private void trackBar2_Scroll(object sender, EventArgs e)
        {
            label2.Text = "Contraste : " + trackBar2.Value;
        }

        private void pictureBox1_Click(object sender, EventArgs e)
        {

        }


        private void TabControl1_SelectedIndexChanged(object sender, EventArgs e)
        {
            // Si on va sur l’onglet 2, on démarre la cam2, sinon on stop
            if (tabControl1.SelectedTab == tabPage2)
                StartCam2();
            else
                StopCam2();
        }


        private void StartCam2()
        {
            if (_cam2 != null && _cam2.IsRunning) return;

            if (_videoDevices == null || _videoDevices.Count < 2)
            {
                MessageBox.Show("Moins de 2 webcams détectées.");
                return;
            }

            // 2e webcam = index 1
            _cam2 = new VideoCaptureDevice(_videoDevices[1].MonikerString);

            // Optionnel : choisir une résolution (sinon la valeur par défaut)
            // var caps = _cam2.VideoCapabilities;
            // _cam2.VideoResolution = caps[0];

            _cam2.NewFrame += Cam2_NewFrame;
            _cam2.Start();
        }

        private void Cam2_NewFrame(object sender, NewFrameEventArgs eventArgs)
        {
            // AForge donne un Bitmap qu’il faut cloner (sinon il sera réutilisé)
            Bitmap frame = (Bitmap)eventArgs.Frame.Clone();

            // Mise à jour UI => Invoke obligatoire
            if (pictureBox1.IsHandleCreated)
            {
                pictureBox1.BeginInvoke(new Action(() =>
                {
                    var old = pictureBox1.Image;
                    pictureBox1.Image = frame;
                    old?.Dispose();
                }));
            }
            else
            {
                frame.Dispose();
            }
        }

        private void StopCam2()
        {
            if (_cam2 == null) return;

            if (_cam2.IsRunning)
            {
                _cam2.NewFrame -= Cam2_NewFrame;
                _cam2.SignalToStop();
                _cam2.WaitForStop();
            }

            _cam2 = null;

            // Nettoyer l’image affichée
            var old = pictureBox1.Image;
            pictureBox1.Image = null;
            old?.Dispose();
        }

        private void Form1_FormClosing(object sender, FormClosingEventArgs e)
        {
            StopCam2();
        }

        private void label2_Click(object sender, EventArgs e)
        {

        }
    }
}
