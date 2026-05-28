using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using AForge.Video.DirectShow;
using OpenCvSharp;
using OpenCvSharp.Extensions;
using System.IO;
using System.IO.Compression;
using System.Drawing.Imaging;

namespace ProntoUI
{

    
    public partial class Form1 : Form
    {
        private enum CalibrationEtat
        {
            Inactive = 0,
            AttentePhotoRecepteur1 = 1,
            AttentePhotoRecepteur2 = 2,
            AttentePhotoEmetteur1 = 3,
            AttentePhotoEmetteur2 = 4
        }

        private FilterInfoCollection _videoDevices;
        private VideoCaptureDevice _cam2;
        private VideoCapture _cvCapture;
        private CancellationTokenSource _cvCaptureLoopCts;
        private bool _isPreviewRunning;
        private int _cameraIndex;

        private Bitmap _lastFrame;
        private readonly object _frameLock = new object();
        private bool _framePresentationPending;

        private Process _pythonProcess;
        private int _capturesAttendues;
        private int _capturesEffectuees;
        private bool _acquisitionEnCours;
        private bool _attenteCaptureCouleur;
        private int _triggersEnAttente;
        private bool _traitementTriggerEnCours;
        private int _intervalMs;
        private CalibrationEtat _calibrationEtat = CalibrationEtat.Inactive;
        private Process _projectionProcess;
        private string _currentProjectPath;
        private string _currentCalibrationReportDirectory;
        private string _dernierDossierAcquisition;

        private const string ProjectExtension = ".pronto3d";
        private static readonly System.Drawing.Size PreferredPreviewSize = new System.Drawing.Size(1280, 720);


        public Form1()
        {
            InitializeComponent();


            // Important : démarrer/stopper selon l’onglet affiché
            tabControl1.SelectedIndexChanged += TabControl1_SelectedIndexChanged;
            this.FormClosing += Form1_FormClosing;

            // Liste des caméras
            _videoDevices = new FilterInfoCollection(FilterCategory.VideoInputDevice);
            // _videoDevices.Count => nombre de webcams détectées
            UpdateWindowTitle();
        }

        private void button1_Click(object sender, EventArgs e)
        {
            if (_attenteCaptureCouleur)
            {
                if (!EnsureCameraReady())
                {
                    return;
                }

                if (!SauvegarderCaptureCouleur())
                {
                    label1.Text = "Aucune image webcam disponible pour la capture couleur";
                    return;
                }

                _attenteCaptureCouleur = false;
                button1.Text = "Lancer Acquisition";
                _ = FinaliserAcquisitionAsync();
                return;
            }

            if (_acquisitionEnCours)
            {
                return;
            }

            if (!EnsureCameraReady())
            {
                return;
            }

            _intervalMs = 2000;
            _capturesAttendues = trackBar1.Value;
            _capturesEffectuees = 0;
            _acquisitionEnCours = true;
            NettoyerDossierAcquisition();
            _dernierDossierAcquisition = GetAcquisitionFolder();
            button1.Text = "Acquisition en cours";
            label1.Text = $"Acquisition en cours (0/{_capturesAttendues})";

            var psi = new ProcessStartInfo
            {
                FileName = "python",
                Arguments = "prgm/franges_fullscreen.py " + trackBar1.Value + " " + _intervalMs,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };

            _pythonProcess = new Process();
            _pythonProcess.StartInfo = psi;

            _pythonProcess.OutputDataReceived += Python_OutputDataReceived;
            _pythonProcess.ErrorDataReceived += Python_ErrorDataReceived;

            _pythonProcess.Start();
            _pythonProcess.BeginOutputReadLine();
            _pythonProcess.BeginErrorReadLine();
        }

        private void trackBar1_Scroll(object sender, EventArgs e)
        {
            label1.Text = "N = " + (trackBar1.Value);
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
            if (_isPreviewRunning) return;

            if (_videoDevices == null || _videoDevices.Count == 0)
            {
                MessageBox.Show("Aucune webcam détectée.");
                return;
            }

            _cameraIndex = _videoDevices.Count >= 2 ? 1 : 0;
            _cam2 = new VideoCaptureDevice(_videoDevices[_cameraIndex].MonikerString);

            if (!StartOpenCvPreview())
            {
                MessageBox.Show("Impossible de demarrer la webcam avec OpenCV.");
            }
        }

        private void StopCam2()
        {
            _cvCaptureLoopCts?.Cancel();
            _cvCaptureLoopCts?.Dispose();
            _cvCaptureLoopCts = null;

            if (_cvCapture != null)
            {
                _cvCapture.Release();
                _cvCapture.Dispose();
                _cvCapture = null;
            }

            _cam2 = null;
            _isPreviewRunning = false;

            var old = pictureBox1.Image;
            pictureBox1.Image = null;
            old?.Dispose();

            lock (_frameLock)
            {
                _lastFrame?.Dispose();
                _lastFrame = null;
            }

            _framePresentationPending = false;
        }

        private bool StartOpenCvPreview()
        {
            _cvCaptureLoopCts?.Cancel();
            _cvCaptureLoopCts?.Dispose();
            _cvCaptureLoopCts = new CancellationTokenSource();

            if (TryOpenCapture(VideoCaptureAPIs.DSHOW, out _cvCapture) || TryOpenCapture(VideoCaptureAPIs.MSMF, out _cvCapture))
            {
                _isPreviewRunning = true;
                StartPreviewLoop(_cvCaptureLoopCts.Token);
                return true;
            }

            _cvCapture = null;
            _isPreviewRunning = false;
            return false;
        }

        private bool TryOpenCapture(VideoCaptureAPIs api, out VideoCapture capture)
        {
            capture = new VideoCapture(_cameraIndex, api);
            if (!capture.IsOpened())
            {
                capture.Dispose();
                capture = null;
                return false;
            }

            capture.Set(VideoCaptureProperties.FourCC, FourCC.MJPG);
            capture.Set(VideoCaptureProperties.FrameWidth, PreferredPreviewSize.Width);
            capture.Set(VideoCaptureProperties.FrameHeight, PreferredPreviewSize.Height);
            capture.Set(VideoCaptureProperties.Fps, 30);
            capture.Set(VideoCaptureProperties.BufferSize, 1);
            capture.Set(VideoCaptureProperties.ConvertRgb, 1);
            ResetCaptureAutoSettings(capture, api);
            return true;
        }

        private void ResetCaptureAutoSettings(VideoCapture capture, VideoCaptureAPIs api)
        {
            // Certains drivers gardent le dernier etat manuel entre deux ouvertures.
            // On remet la camera dans un mode auto "sain" au lancement de la preview.
            TrySetCaptureProperty(capture, VideoCaptureProperties.AutoWB, 1);
            TrySetCaptureProperty(capture, VideoCaptureProperties.AutoFocus, 1);

            if (api == VideoCaptureAPIs.DSHOW)
            {
                TrySetCaptureProperty(capture, VideoCaptureProperties.AutoExposure, 0.75);
            }
            else
            {
                TrySetCaptureProperty(capture, VideoCaptureProperties.AutoExposure, 1);
            }
        }

        private bool TrySetCaptureProperty(VideoCapture capture, VideoCaptureProperties property, double value)
        {
            try
            {
                return capture.Set(property, value);
            }
            catch
            {
                return false;
            }
        }

        private void StartPreviewLoop(CancellationToken token)
        {
            _ = Task.Run(() =>
            {
                using (var frame = new Mat())
                {
                    while (!token.IsCancellationRequested && _cvCapture != null && _cvCapture.IsOpened())
                    {
                        if (!_cvCapture.Read(frame) || frame.Empty())
                        {
                            Thread.Sleep(10);
                            continue;
                        }

                        using (Bitmap bitmap = BitmapConverter.ToBitmap(frame))
                        {
                            lock (_frameLock)
                            {
                                _lastFrame?.Dispose();
                                _lastFrame = (Bitmap)bitmap.Clone();
                            }

                            if (!pictureBox1.IsHandleCreated || _framePresentationPending)
                            {
                                continue;
                            }

                            Bitmap uiBitmap = (Bitmap)bitmap.Clone();
                            _framePresentationPending = true;

                            try
                            {
                                pictureBox1.BeginInvoke(new Action(() =>
                                {
                                    try
                                    {
                                        var old = pictureBox1.Image;
                                        pictureBox1.Image = uiBitmap;
                                        old?.Dispose();
                                    }
                                    finally
                                    {
                                        _framePresentationPending = false;
                                    }
                                }));
                            }
                            catch
                            {
                                uiBitmap.Dispose();
                                _framePresentationPending = false;
                                return;
                            }
                        }
                    }
                }
            }, token);
        }

        private void Form1_FormClosing(object sender, FormClosingEventArgs e)
        {
            TerminerAcquisition();
            TerminerProjection();
            StopCam2();
        }

        private void label2_Click(object sender, EventArgs e)
        {

        }

        private void label1_Click(object sender, EventArgs e)
        {

        }

        private void nouveauProjetToolStripMenuItem_Click(object sender, EventArgs e)
        {
            if (MessageBox.Show("Reinitialiser le projet courant et supprimer les captures locales non enregistrees ?", "Nouveau projet", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
            {
                return;
            }

            ResetLocalProjectData();
            _currentProjectPath = null;
            _calibrationEtat = CalibrationEtat.Inactive;
            button3.Text = "Calibration";
            label1.Text = "Nouveau projet cree";
            UpdateWindowTitle();
        }

        private void ouvrirToolStripMenuItem_Click(object sender, EventArgs e)
        {
            using (var dialog = new OpenFileDialog())
            {
                dialog.Filter = $"Projet Pronto (*{ProjectExtension})|*{ProjectExtension}";
                dialog.Title = "Ouvrir un projet";

                if (dialog.ShowDialog(this) != DialogResult.OK)
                {
                    return;
                }

                OuvrirProjet(dialog.FileName);
            }
        }

        private void enregistrerToolStripMenuItem_Click(object sender, EventArgs e)
        {
            EnregistrerProjet(false);
        }

        private void enregistrerSousToolStripMenuItem_Click(object sender, EventArgs e)
        {
            EnregistrerProjet(true);
        }

        private void quitterToolStripMenuItem_Click(object sender, EventArgs e)
        {
            Close();
        }

        private void parametresWebcamToolStripMenuItem_Click(object sender, EventArgs e)
        {
            if (!EnsureCameraReady())
            {
                MessageBox.Show(this, "Webcam indisponible.", "Parametres webcam", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            try
            {
                _cam2.DisplayPropertyPage(Handle);
            }
            catch (NotSupportedException)
            {
                MessageBox.Show(this, "Cette webcam ne fournit pas de page de proprietes via le driver DirectShow.", "Parametres webcam", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, $"Impossible d'ouvrir les parametres webcam : {ex.Message}", "Parametres webcam", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private void button3_Click(object sender, EventArgs e)
        {
            if (_acquisitionEnCours)
            {
                label1.Text = "Arreter l'acquisition avant la calibration";
                return;
            }

            if (!EnsureCameraReady())
            {
                label1.Text = "Webcam indisponible pour la calibration";
                return;
            }

            switch (_calibrationEtat)
            {
                case CalibrationEtat.Inactive:
                    if (!LancerProjectionBlanche())
                    {
                        label1.Text = "Projection blanche indisponible";
                        return;
                    }

                    _calibrationEtat = CalibrationEtat.AttentePhotoRecepteur1;
                    button3.Text = "Calibration - Recepteur Photo 1";
                    label1.Text = "Fond blanc affiche, prendre la photo recepteur 1";
                    break;

                case CalibrationEtat.AttentePhotoRecepteur1:
                    if (!SauvegarderCaptureCalibrationRecepteur(1))
                    {
                        TerminerProjection();
                        label1.Text = "Impossible de prendre la photo 1";
                        return;
                    }

                    _calibrationEtat = CalibrationEtat.AttentePhotoRecepteur2;
                    button3.Text = "Calibration - Recepteur Photo 2";
                    label1.Text = "Calibration recepteur: photo 1 enregistree, deplacer le plan puis reprendre";
                    break;

                case CalibrationEtat.AttentePhotoRecepteur2:
                    if (!SauvegarderCaptureCalibrationRecepteur(2))
                    {
                        label1.Text = "Impossible de prendre la photo 2 recepteur";
                        return;
                    }

                    TerminerProjection();
                    if (!LancerProjectionDamier())
                    {
                        label1.Text = "Recepteur termine, mais projection damier indisponible pour l'emetteur";
                        return;
                    }

                    _calibrationEtat = CalibrationEtat.AttentePhotoEmetteur1;
                    button3.Text = "Calibration - Emetteur Photo 1";
                    label1.Text = "Calibration recepteur terminee, mire rouge affichee pour l'emetteur";
                    break;

                case CalibrationEtat.AttentePhotoEmetteur1:
                    if (!SauvegarderCaptureCalibrationEmetteur(1))
                    {
                        label1.Text = "Impossible de prendre la photo 1 emetteur";
                        return;
                    }

                    _calibrationEtat = CalibrationEtat.AttentePhotoEmetteur2;
                    button3.Text = "Calibration - Emetteur Photo 2";
                    label1.Text = "Calibration emetteur: photo 1 enregistree, deplacer le plan puis reprendre";
                    break;

                case CalibrationEtat.AttentePhotoEmetteur2:
                    if (!SauvegarderCaptureCalibrationEmetteur(2))
                    {
                        label1.Text = "Impossible de prendre la photo 2 emetteur";
                        return;
                    }

                    TerminerProjection();
                    _calibrationEtat = CalibrationEtat.Inactive;
                    button3.Text = "Calibration";
                    _ = FinaliserCalibrationAsync();
                    break;
            }
        }


        private void Python_OutputDataReceived(object sender, DataReceivedEventArgs e)
        {
            if (string.IsNullOrWhiteSpace(e.Data))
                return;

            string message = e.Data.Trim();

            BeginInvoke(new Action(() =>
            {
                if (message.StartsWith("PHOTO_TRIGGER"))
                {
                    _triggersEnAttente++;
                    _ = TraiterTriggersCaptureAsync();
                }
            }));
        }

        private void Python_ErrorDataReceived(object sender, DataReceivedEventArgs e)
        {
            if (string.IsNullOrWhiteSpace(e.Data))
                return;

            
        }

        private void FaireActionCSharp()
        {
            // Ton action C#
            label1.Text = "Action déclenchée par Python";
        }

        private bool EnsureCameraReady()
        {
            if (_isPreviewRunning)
            {
                return true;
            }

            StartCam2();
            return _isPreviewRunning;
        }

        private async Task TraiterTriggersCaptureAsync()
        {
            if (_traitementTriggerEnCours)
            {
                return;
            }

            _traitementTriggerEnCours = true;

            try
            {
                while (_acquisitionEnCours && _capturesEffectuees < _capturesAttendues && _triggersEnAttente > 0)
                {
                    _triggersEnAttente--;
                    await Task.Delay(Math.Max(1, _intervalMs / 2));

                    bool captureSauvegardee = false;
                    for (int tentative = 0; tentative < 5 && !captureSauvegardee; tentative++)
                    {
                        captureSauvegardee = SauvegarderFrameCourante(_capturesEffectuees + 1);
                        if (!captureSauvegardee)
                        {
                            await Task.Delay(100);
                        }
                    }

                    if (captureSauvegardee)
                    {
                        _capturesEffectuees++;
                        label1.Text = $"Acquisition en cours ({_capturesEffectuees}/{_capturesAttendues})";
                    }
                    else
                    {
                        label1.Text = "Aucune image webcam disponible";
                    }

                    if (_capturesEffectuees >= _capturesAttendues)
                    {
                        TerminerAcquisition();
                    }
                }
            }
            finally
            {
                _traitementTriggerEnCours = false;
            }
        }

        private bool SauvegarderFrameCourante(int indexCapture)
        {
            Bitmap imageASauver = null;

            lock (_frameLock)
            {
                if (_lastFrame != null)
                {
                    imageASauver = (Bitmap)_lastFrame.Clone();
                }
            }

            if (imageASauver == null)
            {
                return false;
            }

            try
            {
                string dossier = GetAcquisitionFolder();
                Directory.CreateDirectory(dossier);

                string nomFichier = $"capture_{indexCapture}.png";
                string cheminComplet = Path.Combine(dossier, nomFichier);

                imageASauver.Save(cheminComplet, ImageFormat.Png);
                SauvegarderDansReconstructionPropre(imageASauver, Path.Combine("captures", "captures", "1"), nomFichier);
                return true;
            }
            finally
            {
                imageASauver.Dispose();
            }
        }

        private Bitmap CopierFrameCourante()
        {
            lock (_frameLock)
            {
                if (_lastFrame != null)
                {
                    return (Bitmap)_lastFrame.Clone();
                }
            }

            return null;
        }

        private string GetAcquisitionFolder()
        {
            return Path.Combine(Application.StartupPath, "captures", "1");
        }

        private string GetWorkspaceRootPath()
        {
            return GetRepositoryRootPath();
        }

        private string GetReconstructionPropreRootPath()
        {
            return Path.Combine(GetRepositoryRootPath(), "reconstruction");
        }

        private string GetReconstructionPropreCapturesFolder(string dossierNom)
        {
            return Path.Combine(GetReconstructionPropreRootPath(), "captures", "captures", dossierNom);
        }

        private void NettoyerDossierAcquisition()
        {
            string dossierLocal = GetAcquisitionFolder();
            if (Directory.Exists(dossierLocal))
            {
                Directory.Delete(dossierLocal, true);
            }

            string dossierPropre = GetReconstructionPropreCapturesFolder("1");
            if (Directory.Exists(dossierPropre))
            {
                Directory.Delete(dossierPropre, true);
            }
        }

        private void SauvegarderDansReconstructionPropre(Bitmap image, string cheminRelatifDossier, string nomFichier)
        {
            string dossier = Path.Combine(GetReconstructionPropreRootPath(), cheminRelatifDossier);
            Directory.CreateDirectory(dossier);
            image.Save(Path.Combine(dossier, nomFichier), ImageFormat.Png);
        }

        private bool SauvegarderCaptureCouleur()
        {
            Bitmap imageASauver = CopierFrameCourante();
            if (imageASauver == null)
            {
                return false;
            }

            try
            {
                string nomFichier = "capture_couleur.png";
                string dossier = string.IsNullOrWhiteSpace(_dernierDossierAcquisition) ? GetAcquisitionFolder() : _dernierDossierAcquisition;
                Directory.CreateDirectory(dossier);
                imageASauver.Save(Path.Combine(dossier, nomFichier), ImageFormat.Png);
                SauvegarderDansReconstructionPropre(imageASauver, Path.Combine("captures", "captures", "1"), nomFichier);
                label1.Text = "Capture couleur sauvegardee";
                return true;
            }
            finally
            {
                imageASauver.Dispose();
            }
        }

        private string GetRepositoryRootPath()
        {
            DirectoryInfo current = new DirectoryInfo(Application.StartupPath);
            while (current != null)
            {
                if (Directory.Exists(Path.Combine(current.FullName, "reconstruction", "src", "reconstruction3d"))
                    && Directory.Exists(Path.Combine(current.FullName, "UI", "ProntoUI", "ProntoUI")))
                {
                    return current.FullName;
                }

                current = current.Parent;
            }

            throw new DirectoryNotFoundException("Impossible de trouver la racine du projet PRONTO.");
        }

        private bool SauvegarderCaptureCalibrationRecepteur(int indexCapture)
        {
            Bitmap imageASauver = CopierFrameCourante();
            if (imageASauver == null)
            {
                return false;
            }

            try
            {
                string dossier = Path.Combine(Application.StartupPath, "captures", "calibration_recepteur");
                Directory.CreateDirectory(dossier);

                string nomFichierLocal = indexCapture == 1 ? "damier0.png" : "damier100.png";
                string cheminLocal = Path.Combine(dossier, nomFichierLocal);
                imageASauver.Save(cheminLocal, ImageFormat.Png);
                SauvegarderDansReconstructionPropre(imageASauver, Path.Combine("captures", "captures", "calibration_recepteur"), nomFichierLocal);

                return true;
            }
            finally
            {
                imageASauver.Dispose();
            }
        }

        private bool SauvegarderCaptureCalibrationEmetteur(int indexCapture)
        {
            Bitmap imageASauver = CopierFrameCourante();
            if (imageASauver == null)
            {
                return false;
            }

            try
            {
                string dossier = Path.Combine(Application.StartupPath, "captures", "calibration_emetteur");
                Directory.CreateDirectory(dossier);

                string nomFichier = indexCapture == 1 ? "capture_calibration_z0.png" : "capture_calibration_z100.png";
                string cheminComplet = Path.Combine(dossier, nomFichier);
                imageASauver.Save(cheminComplet, ImageFormat.Png);
                SauvegarderDansReconstructionPropre(imageASauver, Path.Combine("captures", "captures", "calibration_emetteur"), nomFichier);
                return true;
            }
            finally
            {
                imageASauver.Dispose();
            }
        }

        private bool LancerProjectionBlanche()
        {
            return LancerProjection("white_fullscreen.py");
        }

        private bool LancerProjectionDamier()
        {
            return LancerProjection("damier_fullscreen.py");
        }

        private bool LancerProjection(string scriptName)
        {
            if (_projectionProcess != null && !_projectionProcess.HasExited)
            {
                return true;
            }

            string scriptPath = Path.Combine(Application.StartupPath, "prgm", scriptName);
            if (!File.Exists(scriptPath))
            {
                return false;
            }

            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = "python",
                    Arguments = $"prgm/{scriptName}",
                    UseShellExecute = false,
                    RedirectStandardOutput = false,
                    RedirectStandardError = false,
                    CreateNoWindow = true,
                    WorkingDirectory = Application.StartupPath
                };

                _projectionProcess = new Process();
                _projectionProcess.StartInfo = psi;
                _projectionProcess.Start();
                return true;
            }
            catch
            {
                _projectionProcess = null;
                return false;
            }
        }

        private async Task FinaliserCalibrationAsync()
        {
            button3.Enabled = false;
            label1.Text = "Calibration: creation des masques";

            try
            {
                string workspaceRoot = GetWorkspaceRootPath();
                string cleanRoot = GetReconstructionPropreRootPath();
                string masqueScript = Path.Combine(workspaceRoot, "tools", "creer_masque.py");
                string dossierCalibrationRecepteur = GetReconstructionPropreCapturesFolder("calibration_recepteur");
                string dossierCalibrationEmetteur = GetReconstructionPropreCapturesFolder("calibration_emetteur");
                await RunPythonScriptAsync(masqueScript, workspaceRoot, $"--folder \"{dossierCalibrationRecepteur}\"", createNoWindow: false);
                await RunPythonScriptAsync(masqueScript, workspaceRoot, $"--folder \"{dossierCalibrationEmetteur}\"", createNoWindow: false);

                label1.Text = "Calibration: ajustement des points et calcul MR/ME";
                string anciensDiagnostics = Path.Combine(cleanRoot, "resultats", "diagnostics_calibration");
                if (Directory.Exists(anciensDiagnostics))
                {
                    Directory.Delete(anciensDiagnostics, true);
                }

                string scriptPath = Path.Combine(cleanRoot, "scripts_calibration", "ajuster_points_calibration.py");
                await RunPythonScriptAsync(scriptPath, cleanRoot, "", createNoWindow: false);

                _currentCalibrationReportDirectory = Path.Combine(cleanRoot, "calibration_validee");
                ChargerImagesCalibrationDepuisRapport(_currentCalibrationReportDirectory);
                label1.Text = "Calibration terminee: calcul et compte-rendu disponibles";
            }
            catch (Exception ex)
            {
                label1.Text = "Calibration terminee, mais calcul echoue";
                MessageBox.Show(
                    this,
                    $"Impossible d'executer la calibration Python : {ex.Message}",
                    "Calibration",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
            finally
            {
                button3.Enabled = true;
            }
        }

        private async Task<string> RunPythonScriptAsync(string scriptPath, string workingDirectory, string extraArguments = "", bool createNoWindow = true)
        {
            var psi = new ProcessStartInfo
            {
                FileName = "python",
                Arguments = string.IsNullOrWhiteSpace(extraArguments) ? $"\"{scriptPath}\"" : $"\"{scriptPath}\" {extraArguments}",
                WorkingDirectory = workingDirectory,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = createNoWindow
            };

            using (var process = new Process())
            {
                process.StartInfo = psi;
                var outputBuilder = new StringBuilder();
                var errorBuilder = new StringBuilder();

                process.Start();

                Task<string> outputTask = process.StandardOutput.ReadToEndAsync();
                Task<string> errorTask = process.StandardError.ReadToEndAsync();

                await Task.Run(() => process.WaitForExit());

                outputBuilder.Append(await outputTask);
                errorBuilder.Append(await errorTask);

                if (process.ExitCode != 0)
                {
                    throw new InvalidOperationException(errorBuilder.Length > 0 ? errorBuilder.ToString() : outputBuilder.ToString());
                }

                return outputBuilder.ToString();
            }
        }

        private void ChargerImagesCalibrationDepuisRapport(string reportDirectory)
        {
            string receiverImagePath = Path.Combine(reportDirectory, "recepteur_z0_controle.png");
            string emitterImagePath = Path.Combine(reportDirectory, "emetteur_z0_controle.png");
            string summaryImagePath = Path.Combine(reportDirectory, "recepteur_z100_controle.png");

            SetPictureBoxImage(pictureBoxRenduCalibration, summaryImagePath);
            SetPictureBoxImage(pictureBoxWebcamCalibration, receiverImagePath);
            SetPictureBoxImage(pictureBoxCalibrationDetail, emitterImagePath);
            tabControl1.SelectedTab = tabPage3;
        }

        private void SetPictureBoxImage(PictureBox pictureBox, string imagePath)
        {
            if (!File.Exists(imagePath))
            {
                return;
            }

            using (var stream = new FileStream(imagePath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            using (var image = Image.FromStream(stream))
            {
                var oldImage = pictureBox.Image;
                pictureBox.Image = new Bitmap(image);
                oldImage?.Dispose();
            }
        }

        private void TerminerProjection()
        {
            if (_projectionProcess == null)
            {
                return;
            }

            try
            {
                if (!_projectionProcess.HasExited)
                {
                    _projectionProcess.Kill();
                }
            }
            catch
            {
            }
            finally
            {
                _projectionProcess.Dispose();
                _projectionProcess = null;
            }
        }

        private string GetCapturesRoot()
        {
            return Path.Combine(Application.StartupPath, "captures");
        }

        private string GetMetadataFilePath()
        {
            return Path.Combine(Application.StartupPath, "project_metadata.txt");
        }

        private void ResetLocalProjectData()
        {
            string capturesRoot = GetCapturesRoot();
            if (Directory.Exists(capturesRoot))
            {
                Directory.Delete(capturesRoot, true);
            }

            string metadataPath = GetMetadataFilePath();
            if (File.Exists(metadataPath))
            {
                File.Delete(metadataPath);
            }
        }

        private void UpdateWindowTitle()
        {
            string projectName = string.IsNullOrWhiteSpace(_currentProjectPath)
                ? "Projet non enregistre"
                : Path.GetFileNameWithoutExtension(_currentProjectPath);

            Text = $"Imageur 3D | Pronto | {projectName}";
        }

        private void WriteProjectMetadata(string tempDirectory)
        {
            string metadataPath = Path.Combine(tempDirectory, "project_metadata.txt");
            var lines = new[]
            {
                $"TrackBarN={trackBar1.Value}",
                $"Contraste={trackBar2.Value}",
                $"CalibrationEtat={(int)_calibrationEtat}"
            };
            File.WriteAllLines(metadataPath, lines);
        }

        private void ReadProjectMetadata(string extractedDirectory)
        {
            string metadataPath = Path.Combine(extractedDirectory, "project_metadata.txt");
            if (!File.Exists(metadataPath))
            {
                return;
            }

            foreach (string line in File.ReadAllLines(metadataPath))
            {
                string[] parts = line.Split('=');
                if (parts.Length != 2)
                {
                    continue;
                }

                if (parts[0] == "TrackBarN" && int.TryParse(parts[1], out int trackN))
                {
                    trackBar1.Value = Math.Max(trackBar1.Minimum, Math.Min(trackBar1.Maximum, trackN));
                    label1.Text = "N = " + trackBar1.Value;
                }
                else if (parts[0] == "Contraste" && int.TryParse(parts[1], out int contrast))
                {
                    trackBar2.Value = Math.Max(trackBar2.Minimum, Math.Min(trackBar2.Maximum, contrast));
                    label2.Text = "Contraste : " + trackBar2.Value;
                }
            }
        }

        private void EnregistrerProjet(bool forceSaveAs)
        {
            string targetPath = _currentProjectPath;

            if (forceSaveAs || string.IsNullOrWhiteSpace(targetPath))
            {
                using (var dialog = new SaveFileDialog())
                {
                    dialog.Filter = $"Projet Pronto (*{ProjectExtension})|*{ProjectExtension}";
                    dialog.Title = "Enregistrer le projet";
                    dialog.DefaultExt = ProjectExtension.TrimStart('.');
                    dialog.AddExtension = true;

                    if (dialog.ShowDialog(this) != DialogResult.OK)
                    {
                        return;
                    }

                    targetPath = dialog.FileName;
                }
            }

            if (!targetPath.EndsWith(ProjectExtension, StringComparison.OrdinalIgnoreCase))
            {
                targetPath += ProjectExtension;
            }

            string tempDirectory = Path.Combine(Path.GetTempPath(), "ProntoProject_" + Guid.NewGuid().ToString("N"));

            try
            {
                Directory.CreateDirectory(tempDirectory);

                string capturesRoot = GetCapturesRoot();
                if (Directory.Exists(capturesRoot))
                {
                    CopyDirectory(capturesRoot, Path.Combine(tempDirectory, "captures"));
                }

                WriteProjectMetadata(tempDirectory);

                if (File.Exists(targetPath))
                {
                    File.Delete(targetPath);
                }

                ZipFile.CreateFromDirectory(tempDirectory, targetPath, CompressionLevel.Optimal, false);
                _currentProjectPath = targetPath;
                UpdateWindowTitle();
                label1.Text = $"Projet enregistre : {Path.GetFileName(targetPath)}";
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, $"Impossible d'enregistrer le projet : {ex.Message}", "Enregistrement", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            finally
            {
                if (Directory.Exists(tempDirectory))
                {
                    Directory.Delete(tempDirectory, true);
                }
            }
        }

        private void OuvrirProjet(string projectPath)
        {
            string tempDirectory = Path.Combine(Path.GetTempPath(), "ProntoProject_" + Guid.NewGuid().ToString("N"));

            try
            {
                Directory.CreateDirectory(tempDirectory);
                ZipFile.ExtractToDirectory(projectPath, tempDirectory);

                ResetLocalProjectData();

                string extractedCaptures = Path.Combine(tempDirectory, "captures");
                if (Directory.Exists(extractedCaptures))
                {
                    CopyDirectory(extractedCaptures, GetCapturesRoot());
                }

                ReadProjectMetadata(tempDirectory);
                _currentProjectPath = projectPath;
                _calibrationEtat = CalibrationEtat.Inactive;
                button3.Text = "Calibration";
                UpdateWindowTitle();
                label1.Text = $"Projet ouvert : {Path.GetFileName(projectPath)}";
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, $"Impossible d'ouvrir le projet : {ex.Message}", "Ouverture", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            finally
            {
                if (Directory.Exists(tempDirectory))
                {
                    Directory.Delete(tempDirectory, true);
                }
            }
        }

        private void CopyDirectory(string sourceDirectory, string targetDirectory)
        {
            Directory.CreateDirectory(targetDirectory);

            foreach (string file in Directory.GetFiles(sourceDirectory))
            {
                string targetFile = Path.Combine(targetDirectory, Path.GetFileName(file));
                File.Copy(file, targetFile, true);
            }

            foreach (string directory in Directory.GetDirectories(sourceDirectory))
            {
                string targetSubDirectory = Path.Combine(targetDirectory, Path.GetFileName(directory));
                CopyDirectory(directory, targetSubDirectory);
            }
        }

        private async Task FinaliserAcquisitionAsync()
        {
            button1.Enabled = false;
            label1.Text = "Acquisition: creation du masque";

            try
            {
                string workspaceRoot = GetWorkspaceRootPath();
                string cleanRoot = GetReconstructionPropreRootPath();
                string masqueScript = Path.Combine(workspaceRoot, "tools", "creer_masque.py");
                string dossierObjet = GetReconstructionPropreCapturesFolder("1");
                await RunPythonScriptAsync(masqueScript, workspaceRoot, $"--folder \"{dossierObjet}\"", createNoWindow: false);

                label1.Text = "Acquisition: reconstruction 3D en cours";
                string reconstructionScript = Path.Combine(cleanRoot, "scripts", "lancer_reconstruction.py");
                await RunPythonScriptAsync(reconstructionScript, cleanRoot, "--objets \"1\" --ouvrir-html", createNoWindow: true);
                label1.Text = "Acquisition terminee: reconstruction disponible dans reconstruction\\resultats\\1";
            }
            catch (Exception ex)
            {
                label1.Text = "Acquisition terminee, mais masque ou reconstruction echoue";
                MessageBox.Show(
                    this,
                    $"Impossible de finaliser l'acquisition : {ex.Message}",
                    "Acquisition",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
            finally
            {
                button1.Enabled = true;
                button1.Text = "Lancer Acquisition";
            }
        }

        private void TerminerAcquisition()
        {
            _acquisitionEnCours = false;
            _triggersEnAttente = 0;

            if (_pythonProcess != null)
            {
                try
                {
                    if (!_pythonProcess.HasExited)
                    {
                        _pythonProcess.Kill();
                    }
                }
                catch
                {
                }
                finally
                {
                    _pythonProcess.Dispose();
                    _pythonProcess = null;
                }
            }

            _attenteCaptureCouleur = true;
            button1.Text = "Prendre image couleur";
            label1.Text = $"Acquisition terminee ({_capturesEffectuees}/{_capturesAttendues}) - cliquer pour prendre capture_couleur.png";
        }

    }
}
